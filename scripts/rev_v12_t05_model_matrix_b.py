#!/usr/bin/env python3
"""Revision v12, task t05, agent b: model-source x model-target transfer matrix.

Builds an m x m matrix of Spearman correlations between per-family
FITTING-PERIOD stress curves (source rows) and per-family OUTER-split losses
(target columns) across recovery model families:

    1. linear interpolation / PCHIP boundary (dedicated run, this script)
    2. seasonal-boundary ridge              (dedicated fitting-period run)
    3. donor-covariance ridge               (dedicated fitting-period run)
    4. XGBoost                              (read-only confirmation fit losses)
    5. small bidirectional LSTM (3 seeds, early stopping; dedicated run)
    6. air2stream-equivalent process model  (read-only; no new runs)

The dedicated runs cover the 10 confirmation networks that also carry the
read-only BiLSTM sensitivity losses (intersection of the 42-network first
confirmation roster with the 14-network LSTM roster).  Fitting-period
evaluations use at most 5 placements per station-gap unit and re-use the
repository recovery code paths (development_recovery / recovery_roster /
recurrent_sensitivity helpers).

All numbers in outputs are computed by this script from read-only artifacts
plus the dedicated runs described above.  Nothing outside the agent-b
namespace is written.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import torch
from scipy.interpolate import PchipInterpolator

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

torch.set_num_threads(4)

from stream_recoverability.experiments.development_recovery import (
    _boundary_values,
    _candidate_starts,
    _model_frame,
    read_temperature_panel,
    select_placements,
    year_split,
)
from stream_recoverability.experiments.recovery_roster import (
    _normalise_station,
    _ridge_model,
    season_label,
)
from stream_recoverability.experiments.recurrent_sensitivity import (
    artificial_block_windows,
    nested_training_years,
)
from stream_recoverability.models.lstm_baseline import BidirectionalLSTMImputer

OUTPUT = ROOT / "results/revision_v12/t05_model_matrix/agent_b"
REVIEWER = ROOT / "results/development_v11/reviewer_completion"
AIR2STREAM = ROOT / "results/development_v11/independent_air2stream_equivalent"
SECOND_SCORING = ROOT / "results/development_v11/second_confirmation/scoring"
CONFIRMATION = ROOT / "results/development_v11/route_a_confirmation"
PANEL_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"

NETWORKS = [
    "arso_drava",
    "arso_kamniska_bistrica",
    "foen_aare_aaregebiet",
    "gkd_bayern_alz",
    "gkd_bayern_fraenkische_saale",
    "huc8_02040102",
    "huc8_03010107",
    "lubw_neckar",
    "lubw_rhein",
    "rws_rijn_lek_nederrijn",
]

FIT_GAPS = (7, 30, 90, 180)
NEURAL_GAPS = (7, 30, 90)
PLACEMENTS_PER_UNIT = 5
MIN_TRAIN_DAYS = 365
SEEDS = (0, 1, 2)
NEURAL_CONFIG = {
    "hidden_size": 16,
    "n_layers": 1,
    "epochs": 40,
    "patience": 6,
    "batch_size": 8,
    "max_windows": 24,
    "validation_windows": 8,
    "window_length": 128,
}

FAMILY_NAMES = {
    "linear_boundary": "1_linear_pchip_boundary",
    "pchip_record": "1_pchip_record_variant",
    "seasonal_boundary_ridge": "2_seasonal_boundary_ridge",
    "donor_blup_ridge": "3_donor_covariance_ridge",
    "xgboost_b_d": "4_xgboost",
    "neural_bilstm": "5_bilstm",
    "air2stream": "6_air2stream",
}


def spearman(frame: pd.DataFrame, left: str, right: str) -> float | None:
    usable = frame[[left, right]].dropna()
    if len(usable) < 3 or usable[left].nunique() < 2 or usable[right].nunique() < 2:
        return None
    return float(usable[left].corr(usable[right], method="spearman"))


def ols_slope(x: pd.Series, y: pd.Series) -> float | None:
    usable = pd.concat([x, y], axis=1).dropna()
    if len(usable) < 3 or usable.iloc[:, 0].nunique() < 2:
        return None
    design = np.column_stack(
        [np.ones(len(usable)), usable.iloc[:, 0].to_numpy(dtype=float)]
    )
    coefficient = np.linalg.lstsq(
        design, usable.iloc[:, 1].to_numpy(dtype=float), rcond=None
    )[0]
    return float(coefficient[1])


def _season_of(dates) -> np.ndarray:
    parsed = pd.to_datetime(pd.Series(dates), errors="coerce", utc=False)
    return season_label(parsed)


def curve_by_season(source_placements: pd.DataFrame) -> pd.DataFrame:
    """Collapse fitting-period placements to (network, station, gap, season)."""

    return (
        source_placements.groupby(
            ["network_id", "station_id", "gap_length", "season"], as_index=False
        )["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "source_mae"})
    )


def map_curve_to_targets(curve: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Attach season-matched fitting-period curve values to target placements."""

    merged = targets.merge(
        curve,
        on=["network_id", "station_id", "gap_length", "season"],
        how="left",
        validate="many_to_one",
    )
    merged = merged.dropna(subset=["source_mae"]).copy()
    return merged


def aggregate_units(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Placement rows -> station-gap units -> network units."""

    station_gap = (
        merged.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(source=("source_mae", "mean"), target=("target_mae", "mean"))
        .dropna(subset=["source", "target"])
    )
    network = (
        station_gap.groupby("network_id", as_index=False)
        .mean(numeric_only=True)
        .dropna(subset=["source", "target"])
    )
    return station_gap, network


def cell_metrics(source_curve: pd.DataFrame, target_placements: pd.DataFrame) -> dict:
    """One (source family, target family) cell of the transfer matrix."""

    if source_curve.empty or target_placements.empty:
        return {
            "station_gap_spearman": None,
            "network_spearman": None,
            "station_gap_slope": None,
            "network_slope": None,
            "n_units": 0,
            "n_networks": 0,
            "n_placements": 0,
        }
    merged = map_curve_to_targets(source_curve, target_placements)
    station_gap, network = aggregate_units(merged)
    return {
        "station_gap_spearman": spearman(station_gap, "source", "target"),
        "network_spearman": spearman(network, "source", "target"),
        "station_gap_slope": ols_slope(station_gap["source"], station_gap["target"]),
        "network_slope": ols_slope(network["source"], network["target"]),
        "n_units": len(station_gap),
        "n_networks": len(network),
        "n_placements": len(merged),
    }


def read_confirmation_panel(network: str) -> pd.DataFrame:
    return read_temperature_panel(
        str(PANEL_ROOT / network / "daily_wide_temperature.csv")
    )


def nested_masks(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.Series, tuple, tuple]:
    """Outer and nested inner splits; returns (outer_train, inner_fit, inner_score, fit_years, score_years)."""

    outer_train, _, _ = year_split(index)
    training_index = index[outer_train]
    inner_relative, inner_fit_years, inner_score_years = year_split(training_index)
    inner_fit = pd.Series(False, index=index)
    inner_fit.loc[training_index] = inner_relative.to_numpy(dtype=bool)
    inner_score = outer_train & ~inner_fit
    return outer_train, inner_fit, inner_score, inner_fit_years, inner_score_years


def run_fitting_period_families_123() -> pd.DataFrame:
    """Dedicated fitting-period stress curves for families 1 (linear boundary
    + pchip-record variant), 2 (seasonal-boundary ridge), 3 (donor ridge).

    Uses the same nested split as the read-only XGBoost fitting-period curve
    (confirmation_empirical_fit_losses.csv) and at most 5 placements per
    station-gap unit.  Completed results are resumed from disk.
    """

    cached = OUTPUT / "fit_losses_families_1_3.csv"
    if cached.is_file():
        return pd.read_csv(cached, dtype={"network_id": str, "station_id": str})
    placements = pd.read_csv(
        CONFIRMATION / "placement_losses.csv", dtype={"network_id": str}
    )
    rows: list[dict[str, object]] = []
    for ordinal, network in enumerate(NETWORKS, start=1):
        print(f"fit-period families 1-3 [{ordinal}/{len(NETWORKS)}]: {network}", flush=True)
        panel = read_confirmation_panel(network)
        daily = panel.copy().sort_index().asfreq("D")
        daily.columns = daily.columns.astype(str)
        outer_train, inner_fit, inner_score, fit_years, score_years = nested_masks(
            daily.index
        )
        network_rows = placements.loc[
            placements["network_id"].astype(str).eq(network)
            & placements["information_condition"].eq("B_union_D")
        ]
        for raw_station, station_rows in network_rows.groupby("station_id", sort=False):
            try:
                station = _normalise_station(raw_station, daily.columns)
            except KeyError:
                continue
            donor_text = str(station_rows["donor_station_ids"].iloc[0])
            donors = tuple(
                _normalise_station(value, daily.columns)
                for value in donor_text.split("|")
                if value and value != "nan"
            )
            if not donors or int((inner_fit & daily[station].notna()).sum()) < MIN_TRAIN_DAYS:
                continue
            empty_aux = pd.DataFrame(index=daily.index)
            seasonal_frame = _model_frame(
                daily,
                empty_aux,
                target_station=station,
                donors=(),
                meteorology=(),
                hydraulics=(),
                train_mask=inner_fit,
            )
            donor_frame = _model_frame(
                daily,
                empty_aux,
                target_station=station,
                donors=donors,
                meteorology=(),
                hydraulics=(),
                train_mask=inner_fit,
            )
            try:
                models = {
                    "seasonal_boundary_ridge": _ridge_model(
                        seasonal_frame, daily[station], inner_fit
                    ),
                    "donor_blup_ridge": _ridge_model(
                        donor_frame, daily[station], inner_fit
                    ),
                }
            except ValueError:
                continue
            target = daily[station]
            observed_all = target.notna()
            anchor_mask = (observed_all & outer_train).to_numpy(dtype=bool)
            for gap in FIT_GAPS:
                candidates = _candidate_starts(
                    daily,
                    empty_aux,
                    target_station=station,
                    donors=donors,
                    meteorology=(),
                    hydraulics=(),
                    evaluation_mask=inner_score,
                    gap_length=gap,
                )
                if not len(candidates):
                    continue
                chosen = select_placements(candidates, count=PLACEMENTS_PER_UNIT)
                for placement, start in enumerate(int(value) for value in chosen):
                    truth = target.iloc[start : start + gap].to_numpy(dtype=float)
                    if not np.isfinite(truth).all():
                        continue
                    boundary = _boundary_values(target, start, gap)
                    linear_mae = float(np.mean(np.abs(boundary - truth)))
                    pchip_mae = _pchip_record_mae(
                        target, anchor_mask, start, gap, truth
                    )
                    rows.append(
                        {
                            "network_id": network,
                            "station_id": station,
                            "gap_length": gap,
                            "season": _season_of([daily.index[start]])[0],
                            "placement": placement,
                            "gap_start": daily.index[start],
                            "model_family": "linear_boundary",
                            "mae_deg_c": linear_mae,
                            "inner_fit_years": "|".join(map(str, fit_years)),
                            "inner_score_years": "|".join(map(str, score_years)),
                        }
                    )
                    if pchip_mae is not None:
                        rows.append(
                            {
                                "network_id": network,
                                "station_id": station,
                                "gap_length": gap,
                                "season": _season_of([daily.index[start]])[0],
                                "placement": placement,
                                "gap_start": daily.index[start],
                                "model_family": "pchip_record",
                                "mae_deg_c": pchip_mae,
                                "inner_fit_years": "|".join(map(str, fit_years)),
                                "inner_score_years": "|".join(map(str, score_years)),
                            }
                        )
                    for family, model in models.items():
                        prediction_frame = (
                            seasonal_frame
                            if family == "seasonal_boundary_ridge"
                            else donor_frame
                        ).iloc[start : start + gap].copy()
                        prediction_frame["B__boundary_temperature"] = boundary
                        if prediction_frame.isna().any(axis=None):
                            continue
                        predicted = model.predict(prediction_frame)
                        rows.append(
                            {
                                "network_id": network,
                                "station_id": station,
                                "gap_length": gap,
                                "season": _season_of([daily.index[start]])[0],
                                "placement": placement,
                                "gap_start": daily.index[start],
                                "model_family": family,
                                "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                                "inner_fit_years": "|".join(map(str, fit_years)),
                                "inner_score_years": "|".join(map(str, score_years)),
                            }
                        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no fitting-period placements produced")
    return frame


def _pchip_record_mae(
    target: pd.Series,
    anchors_mask: np.ndarray,
    start: int,
    gap: int,
    truth: np.ndarray,
    *,
    window_days: int = 2000,
) -> float | None:
    """PCHIP boundary fill: shape-preserving cubic through fitting-period
    observed values within a local window around the gap (gap days excluded).

    ``anchors_mask`` marks days whose observed values the model may use
    (fitting-period days; the two observed gap boundary days are added by the
    caller for outer evaluations).  The gap lies strictly between its two
    observed boundary days, so the fill is interpolation (extrapolate=False
    never triggers).
    """

    mid = (2 * start + gap) / 2.0
    local = np.abs(np.arange(len(target), dtype=float) - mid) <= window_days
    gap_mask = np.zeros(len(target), dtype=bool)
    gap_mask[start : start + gap] = True
    anchors = anchors_mask & local & ~gap_mask
    if int(anchors.sum()) < 2:
        return None
    x = np.flatnonzero(anchors).astype(float)
    y = target.to_numpy(dtype=float)[anchors]
    interpolator = PchipInterpolator(x, y, extrapolate=False)
    fill = interpolator(np.arange(start, start + gap, dtype=float))
    if not np.isfinite(fill).all():
        return None
    return float(np.mean(np.abs(fill - truth)))


def run_family1_outer_targets() -> pd.DataFrame:
    """Outer-split losses for family 1 (linear boundary; pchip-record variant)
    on the exact B_union_D placements scored by the read-only roster.
    Completed results are resumed from disk."""

    cached = OUTPUT / "target_losses_family_1.csv"
    if cached.is_file():
        return pd.read_csv(cached, dtype={"network_id": str, "station_id": str})
    roster = pd.read_csv(
        REVIEWER / "confirmation_model_roster_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    placements = roster.loc[
        roster["model_family"].eq("xgboost_b_d")
        & roster["network_id"].isin(NETWORKS)
    ].copy()
    rows: list[dict[str, object]] = []
    for network, group in placements.groupby("network_id", sort=False):
        panel = read_confirmation_panel(str(network))
        daily = panel.copy().sort_index().asfreq("D")
        daily.columns = daily.columns.astype(str)
        outer_train, _, _, _, _ = nested_masks(daily.index)
        observed = daily.notna().to_numpy(dtype=bool)
        for item in group.itertuples(index=False):
            try:
                station = _normalise_station(str(item.station_id), daily.columns)
            except KeyError:
                continue
            start = daily.index.get_indexer([pd.Timestamp(item.gap_start)])[0]
            gap = int(item.gap_length)
            if start < 1 or start + gap >= len(daily):
                continue
            target = daily[station]
            truth = target.iloc[start : start + gap].to_numpy(dtype=float)
            if not np.isfinite(truth).all():
                continue
            boundary = _boundary_values(target, start, gap)
            season = _season_of([item.gap_start])[0]
            rows.append(
                {
                    "network_id": network,
                    "station_id": station,
                    "gap_length": gap,
                    "placement": int(item.placement),
                    "gap_start": pd.Timestamp(item.gap_start),
                    "season": season,
                    "model_family": "linear_boundary",
                    "mae_deg_c": float(np.mean(np.abs(boundary - truth))),
                }
            )
            feature_index = daily.columns.get_loc(station)
            anchor_mask = observed[:, feature_index] & outer_train.to_numpy(dtype=bool)
            anchor_mask[start - 1] = True
            anchor_mask[start + gap] = True
            pchip_mae = _pchip_record_mae(target, anchor_mask, start, gap, truth)
            if pchip_mae is not None:
                rows.append(
                    {
                        "network_id": network,
                        "station_id": station,
                        "gap_length": gap,
                        "placement": int(item.placement),
                        "gap_start": pd.Timestamp(item.gap_start),
                        "season": season,
                        "model_family": "pchip_record",
                        "mae_deg_c": pchip_mae,
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no family-1 outer targets produced")
    return frame


def neural_usable_years(
    daily: pd.DataFrame, fit_years: Sequence[int], min_concurrent_days: int = 30
) -> tuple[int, ...]:
    """Fitting years with a minimally concurrent record; prefer two features
    and fall back to one (networks whose donors start late)."""

    concurrency = daily.notna().sum(axis=1)
    for minimum_features in (2, 1):
        years = [
            int(year)
            for year in fit_years
            if int((concurrency[daily.index.year == year] >= minimum_features).sum())
            >= min_concurrent_days
        ]
        if years:
            return tuple(years)
    return ()


def run_neural() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train a small bidirectional LSTM per network with early stopping on a
    validation slice of the fitting period; score artificial gaps inside the
    fitting period (inner score years).  Three seeds.  Completed results are
    resumed from disk."""

    cached_source = OUTPUT / "neural_fit_sources.csv"
    cached_histories = OUTPUT / "neural_histories.csv"
    cached_summary = OUTPUT / "neural_summary.csv"
    if cached_source.is_file() and cached_histories.is_file() and cached_summary.is_file():
        return (
            pd.read_csv(cached_source, dtype={"network_id": str, "station_id": str}),
            pd.read_csv(cached_histories, dtype={"network_id": str}),
            pd.read_csv(cached_summary, dtype={"network_id": str}),
        )
    placements = pd.read_csv(
        CONFIRMATION / "placement_losses.csv", dtype={"network_id": str}
    )
    source_rows: list[dict[str, object]] = []
    history_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for ordinal, network in enumerate(NETWORKS, start=1):
        print(f"neural [{ordinal}/{len(NETWORKS)}]: {network}", flush=True)
        panel = read_confirmation_panel(network)
        daily = panel.copy().sort_index().asfreq("D")
        daily.columns = daily.columns.astype(str)
        outer_train, _, inner_score, fit_years, score_years = nested_masks(
            daily.index
        )
        usable_years = neural_usable_years(daily, fit_years)
        if len(usable_years) < 2:
            print(f"  skip {network}: <2 usable fitting years", flush=True)
            continue
        fit_split_years, validation_years = nested_training_years(usable_years)
        network_rows = placements.loc[
            placements["network_id"].astype(str).eq(network)
            & placements["information_condition"].eq("B_union_D")
        ]
        roster_stations = {
            str(value) for value in network_rows["station_id"].unique()
        }
        for seed in SEEDS:
            try:
                train_values, train_mask = artificial_block_windows(
                    daily,
                    fit_split_years,
                    gap_lengths=NEURAL_GAPS,
                    window_length=NEURAL_CONFIG["window_length"],
                    max_windows=NEURAL_CONFIG["max_windows"],
                    seed=seed,
                )
                validation_values, validation_mask = artificial_block_windows(
                    daily,
                    validation_years,
                    gap_lengths=NEURAL_GAPS,
                    window_length=NEURAL_CONFIG["window_length"],
                    max_windows=NEURAL_CONFIG["validation_windows"],
                    seed=seed + 1,
                )
            except ValueError as error:
                print(f"  skip {network} seed {seed}: {error}", flush=True)
                continue
            usable_features = (np.isfinite(train_values) & ~train_mask).any(
                axis=(0, 1)
            ) & (np.isfinite(validation_values) & ~validation_mask).any(axis=(0, 1))
            if int(usable_features.sum()) < 1:
                print(f"  skip {network} seed {seed}: no usable features", flush=True)
                continue
            columns = daily.columns[usable_features]
            train_values = train_values[:, :, usable_features]
            train_mask = train_mask[:, :, usable_features]
            validation_values = validation_values[:, :, usable_features]
            validation_mask = validation_mask[:, :, usable_features]
            train_keep = train_mask.any(axis=(1, 2)) & (
                ~train_mask | np.isfinite(train_values)
            ).all(axis=(1, 2))
            validation_keep = validation_mask.any(axis=(1, 2)) & (
                ~validation_mask | np.isfinite(validation_values)
            ).all(axis=(1, 2))
            if not train_keep.any() or not validation_keep.any():
                print(f"  skip {network} seed {seed}: no NaN-free windows", flush=True)
                continue
            model = BidirectionalLSTMImputer(
                int(usable_features.sum()),
                hidden_size=NEURAL_CONFIG["hidden_size"],
                n_layers=NEURAL_CONFIG["n_layers"],
                seed=seed,
            ).fit(
                train_values[train_keep],
                train_mask[train_keep],
                validation_values=validation_values[validation_keep],
                validation_mask=validation_mask[validation_keep],
                epochs=NEURAL_CONFIG["epochs"],
                batch_size=NEURAL_CONFIG["batch_size"],
                patience=NEURAL_CONFIG["patience"],
            )
            history = model.history_
            history_rows.extend(
                {
                    "network_id": network,
                    "seed": seed,
                    "epoch": epoch + 1,
                    "train_loss": float(history["train_loss"][epoch]),
                    "validation_loss": float(history["validation_loss"][epoch]),
                }
                for epoch in range(len(history["train_loss"]))
            )
            summary_rows.append(
                {
                    "network_id": network,
                    "seed": seed,
                    "n_features": int(usable_features.sum()),
                    "fit_years": "|".join(map(str, fit_split_years)),
                    "validation_years": "|".join(map(str, validation_years)),
                    "score_years": "|".join(map(str, score_years)),
                    "n_training_windows": len(train_values),
                    "n_validation_windows": len(validation_values),
                    "epochs_ran": int(history["epochs_ran"]),
                    "best_epoch": int(history["best_epoch"]),
                    "best_validation_loss": float(history["best_validation_loss"]),
                    "hit_epoch_limit": bool(history["hit_epoch_limit"]),
                }
            )
            scored = score_neural_fit_period(
                network,
                model,
                daily,
                columns,
                roster_stations,
                inner_score,
                outer_train,
                seed=seed,
            )
            for item in scored.itertuples(index=False):
                source_rows.append(
                    {
                        "network_id": network,
                        "station_id": item.station_id,
                        "gap_length": int(item.gap_length),
                        "season": item.season,
                        "placement": int(item.placement),
                        "gap_start": item.gap_start,
                        "model_family": "neural_bilstm",
                        "mae_deg_c": float(item.mae_deg_c),
                        "seed": seed,
                    }
                )
    source = pd.DataFrame(source_rows)
    histories = pd.DataFrame(history_rows)
    summary = pd.DataFrame(summary_rows)
    if source.empty or histories.empty:
        raise RuntimeError("neural runs produced no rows")
    return source, histories, summary


def score_neural_fit_period(
    network_id: str,
    model: object,
    daily: pd.DataFrame,
    columns: pd.Index,
    roster_stations: set[str],
    inner_score: pd.Series,
    outer_train: pd.Series,
    *,
    seed: int,
) -> pd.DataFrame:
    """Artificial gaps wholly inside the fitting period (gap block in the
    inner score years; 128-day context window inside the fitting period)."""

    window_length = NEURAL_CONFIG["window_length"]
    values = daily.loc[:, columns].to_numpy(dtype=np.float32)
    finite = np.isfinite(values)
    inner = inner_score.to_numpy(dtype=bool)
    outer = outer_train.to_numpy(dtype=bool)
    rows: list[dict[str, object]] = []
    for feature, station in enumerate(columns):
        if str(station) not in roster_stations:
            continue
        for gap in NEURAL_GAPS:
            candidates: list[int] = []
            for block_start in range(1, len(daily) - gap - 1):
                if not inner[block_start]:
                    continue
                left_context = (window_length - gap) // 2
                window_start = block_start - left_context
                window_end = window_start + window_length
                if window_start < 0 or window_end > len(daily):
                    continue
                if not outer[window_start:window_end].all():
                    continue
                if not finite[block_start : block_start + gap, feature].all():
                    continue
                sample = values[window_start:window_end]
                if not np.isfinite(sample).all():
                    continue
                candidates.append(block_start)
            if not candidates:
                continue
            chosen = select_placements(
                np.asarray(candidates, dtype=int), count=PLACEMENTS_PER_UNIT
            )
            for placement, block_start in enumerate(int(value) for value in chosen):
                left_context = (window_length - gap) // 2
                window_start = block_start - left_context
                relative = block_start - window_start
                sample = values[window_start : window_start + window_length].copy()
                hidden = np.zeros_like(sample, dtype=bool)
                hidden[relative : relative + gap, feature] = True
                prediction = model.predict(sample, hidden)
                predicted = prediction[relative : relative + gap, feature]
                truth = sample[relative : relative + gap, feature]
                rows.append(
                    {
                        "network_id": network_id,
                        "station_id": str(station),
                        "gap_length": gap,
                        "season": _season_of([daily.index[block_start]])[0],
                        "placement": placement,
                        "gap_start": daily.index[block_start],
                        "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                    }
                )
    return pd.DataFrame(rows)


def build_target_tables() -> dict[str, pd.DataFrame]:
    """Placement-level outer losses per target family (read-only + family 1)."""

    roster = pd.read_csv(
        REVIEWER / "confirmation_model_roster_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    roster = roster.loc[roster["network_id"].isin(NETWORKS)].copy()
    roster["season"] = _season_of(roster["gap_start"])
    tables: dict[str, pd.DataFrame] = {}
    for family in ("seasonal_boundary_ridge", "donor_blup_ridge", "xgboost_b_d"):
        sub = roster.loc[roster["model_family"].eq(family)].copy()
        tables[family] = sub.rename(columns={"mae_deg_c": "target_mae"})[
            ["network_id", "station_id", "gap_length", "placement", "gap_start", "season", "target_mae"]
        ]
    lstm = pd.read_csv(
        REVIEWER / "lstm_sensitivity_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    lstm = lstm.loc[lstm["network_id"].isin(NETWORKS)].copy()
    lstm["season"] = _season_of(lstm["gap_start"])
    tables["neural_bilstm"] = lstm.rename(columns={"lstm_mae_deg_c": "target_mae"})[
        ["network_id", "station_id", "gap_length", "placement", "gap_start", "season", "target_mae"]
    ]
    return tables


def crosschecks() -> pd.DataFrame:
    """Reproduce the four known reference values from read-only artifacts."""

    rows: list[dict[str, object]] = []

    second = pd.read_csv(
        SECOND_SCORING / "empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    second = second.loc[second["gap_length"].isin((7, 30, 90, 180))]
    unit = second.groupby(["network_id", "station_id", "gap_length"], as_index=False).agg(
        source=("empirical_transfer_prediction", "mean"),
        target=("observed_recovery_loss", "mean"),
    )
    rows.append(
        {
            "check": "empirical_vs_xgboost_second_panel_supported_horizons",
            "level": "station_gap",
            "value": spearman(unit, "source", "target"),
            "n_units": len(unit),
            "reference": 0.945,
        }
    )

    lstm = pd.read_csv(
        REVIEWER / "lstm_sensitivity_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    unit = lstm.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        source=("empirical_transfer_prediction", "first"),
        target=("lstm_mae_deg_c", "mean"),
    )
    network = unit.groupby("network_id", as_index=False).mean(numeric_only=True)
    rows.append(
        {
            "check": "xgboost_source_vs_bilstm_loss",
            "level": "station_gap",
            "value": spearman(unit, "source", "target"),
            "n_units": len(unit),
            "reference": 0.338,
        }
    )
    rows.append(
        {
            "check": "xgboost_source_vs_bilstm_loss",
            "level": "network",
            "value": spearman(network, "source", "target"),
            "n_units": len(network),
            "reference": 0.631,
        }
    )

    air2 = pd.read_csv(
        AIR2STREAM / "station_gap_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    network = air2.groupby("network_id", as_index=False).mean(numeric_only=True)
    rows.append(
        {
            "check": "xgboost_source_vs_air2stream_loss",
            "level": "station_gap",
            "value": spearman(air2, "empirical_transfer_prediction", "air2stream_mae_deg_c"),
            "n_units": len(air2),
            "reference": 0.173,
        }
    )
    rows.append(
        {
            "check": "xgboost_source_vs_air2stream_loss",
            "level": "network",
            "value": spearman(network, "empirical_transfer_prediction", "air2stream_mae_deg_c"),
            "n_units": len(network),
            "reference": 0.238,
        }
    )

    roster = pd.read_csv(
        REVIEWER / "model_roster_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    for family, reference in (
        ("donor_blup_ridge", 0.387),
        ("seasonal_boundary_ridge", 0.430),
        ("xgboost_b_d", 0.565),
    ):
        sub = roster.loc[roster["model_family"].eq(family)]
        network = sub.groupby("network_id", as_index=False).agg(
            source=("predicted_model_loss", "mean"),
            target=("model_loss", "mean"),
        )
        rows.append(
            {
                "check": f"descriptor_predictor_vs_{family}_loss",
                "level": "network",
                "value": spearman(network, "source", "target"),
                "n_units": len(network),
                "reference": reference,
            }
        )
    return pd.DataFrame(rows)


def plot_convergence(histories: pd.DataFrame, summary: pd.DataFrame) -> Path:
    """Early-stopping validation curves: one small panel per network, three
    seeds overlaid, training loss dashed and validation loss solid."""

    networks = sorted(histories["network_id"].unique())
    figure, axes = plt.subplots(
        nrows=(len(networks) + 1) // 2, ncols=2, figsize=(11, 2.6 * ((len(networks) + 1) // 2))
    )
    flat = np.asarray(axes).reshape(-1)
    for axis, network in zip(flat, networks):
        for seed, group in histories.loc[histories["network_id"].eq(network)].groupby("seed"):
            axis.plot(
                group["epoch"], group["train_loss"], linestyle="--", linewidth=0.9,
                color=plt.cm.viridis(seed / (len(SEEDS) - 1)), alpha=0.8,
            )
            axis.plot(
                group["epoch"], group["validation_loss"], linewidth=1.2,
                color=plt.cm.viridis(seed / (len(SEEDS) - 1)), alpha=0.9,
            )
        best = summary.loc[summary["network_id"].eq(network), "best_validation_loss"]
        axis.set_title(f"{network} (best val {best.median():.3f})", fontsize=8)
        axis.set_yscale("log")
        axis.tick_params(labelsize=7)
    for axis in flat[len(networks):]:
        axis.set_visible(False)
    figure.suptitle("Neural fitting-period training (dashed) / validation (solid) loss by seed", fontsize=10)
    figure.tight_layout()
    path = OUTPUT / "neural_convergence.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def full_roster_extension() -> pd.DataFrame:
    """XGBoost source row and statistical-family columns at the full 42-network
    first-confirmation scale (read-only only), for big-sample context."""

    fit = pd.read_csv(
        REVIEWER / "confirmation_empirical_fit_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    curve = curve_by_season(fit)
    roster = pd.read_csv(
        REVIEWER / "confirmation_model_roster_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    roster["season"] = _season_of(roster["gap_start"])
    rows: list[dict[str, object]] = []
    for family in ("seasonal_boundary_ridge", "donor_blup_ridge", "xgboost_b_d"):
        targets = roster.loc[roster["model_family"].eq(family)].rename(
            columns={"mae_deg_c": "target_mae"}
        )
        metrics = cell_metrics(curve, targets)
        for key, value in metrics.items():
            rows.append(
                {
                    "source_family": "4_xgboost",
                    "target_family": FAMILY_NAMES[family],
                    "metric": key,
                    "value": value,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    started = time.time()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    print("== cross-checks from read-only artifacts ==", flush=True)
    checks = crosschecks()
    checks.to_csv(OUTPUT / "crosschecks.csv", index=False)

    print("== dedicated fitting-period families 1-3 ==", flush=True)
    fit_123 = run_fitting_period_families_123()
    fit_123.to_csv(OUTPUT / "fit_losses_families_1_3.csv", index=False)

    print("== family-1 outer targets ==", flush=True)
    target_1 = run_family1_outer_targets()
    target_1.to_csv(OUTPUT / "target_losses_family_1.csv", index=False)

    print("== neural runs ==", flush=True)
    neural_sources, neural_histories, neural_summary = run_neural()
    neural_sources.to_csv(OUTPUT / "neural_fit_sources.csv", index=False)
    neural_histories.to_csv(OUTPUT / "neural_histories.csv", index=False)
    neural_summary.to_csv(OUTPUT / "neural_summary.csv", index=False)
    plot_convergence(neural_histories, neural_summary)

    print("== build matrix ==", flush=True)
    sources: dict[str, pd.DataFrame] = {}
    for family in ("linear_boundary", "pchip_record", "seasonal_boundary_ridge", "donor_blup_ridge"):
        sub = fit_123.loc[fit_123["model_family"].eq(family)]
        sources[family] = curve_by_season(sub)
    xgboost_fit = pd.read_csv(
        REVIEWER / "confirmation_empirical_fit_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    xgboost_fit = xgboost_fit.loc[xgboost_fit["network_id"].isin(NETWORKS)]
    sources["xgboost_b_d"] = curve_by_season(xgboost_fit)

    seed_averaged = (
        neural_sources.groupby(
            ["network_id", "station_id", "gap_length", "season"], as_index=False
        )["mae_deg_c"]
        .mean()
    )
    sources["neural_bilstm"] = seed_averaged.rename(columns={"mae_deg_c": "source_mae"})

    targets = build_target_tables()
    family1_target = target_1.loc[target_1["model_family"].eq("linear_boundary")]
    targets["linear_boundary"] = family1_target.rename(columns={"mae_deg_c": "target_mae"})[
        ["network_id", "station_id", "gap_length", "placement", "gap_start", "season", "target_mae"]
    ]

    air2 = pd.read_csv(
        AIR2STREAM / "station_gap_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )

    matrix_rows: list[dict[str, object]] = []
    for source_family, curve in sources.items():
        for target_family, target_placements in targets.items():
            if target_family == "neural_bilstm" and source_family == "neural_bilstm":
                # neural source curves were restricted to roster stations; keep
                # the generic machinery (it already matches on those stations)
                pass
            metrics = cell_metrics(curve, target_placements)
            for key in (
                "station_gap_spearman",
                "network_spearman",
                "station_gap_slope",
                "network_slope",
                "n_units",
                "n_networks",
                "n_placements",
            ):
                matrix_rows.append(
                    {
                        "source_family": FAMILY_NAMES[source_family],
                        "target_family": FAMILY_NAMES[target_family],
                        "metric": key,
                        "value": metrics[key],
                    }
                )

    air2_cells = [
        ("xgboost_b_d", "empirical_transfer_prediction", "air2stream_mae_deg_c", "4_xgboost", "6_air2stream"),
    ]
    air2_network = air2.groupby("network_id", as_index=False).mean(numeric_only=True)
    air2_panel_rows: list[dict[str, object]] = []
    for source_label, source_col, target_col, src_name, tgt_name in air2_cells:
        frame = air2[[source_col, target_col]].dropna().copy()
        frame.columns = ["source", "target"]
        net = air2_network[[source_col, target_col]].dropna().copy()
        net.columns = ["source", "target"]
        metrics = {
            "station_gap_spearman": spearman(frame, "source", "target"),
            "network_spearman": spearman(net, "source", "target"),
            "station_gap_slope": ols_slope(frame["source"], frame["target"]),
            "network_slope": ols_slope(net["source"], net["target"]),
            "n_units": len(frame),
            "n_networks": len(net),
            "n_placements": len(frame),
        }
        for key, value in metrics.items():
            matrix_rows.append(
                {
                    "source_family": src_name,
                    "target_family": tgt_name,
                    "metric": key,
                    "value": value,
                }
            )
            air2_panel_rows.append(
                {
                    "source_family": src_name,
                    "target_family": tgt_name,
                    "metric": key,
                    "value": value,
                }
            )

    for source_label, source_col, target_col in (
        ("xgboost_source", "empirical_transfer_prediction", "xgboost_mae_deg_c"),
    ):
        frame = air2[[source_col, target_col]].dropna().copy()
        frame.columns = ["source", "target"]
        net = air2_network[[source_col, target_col]].dropna().copy()
        net.columns = ["source", "target"]
        for key, value in {
            "station_gap_spearman": spearman(frame, "source", "target"),
            "network_spearman": spearman(net, "source", "target"),
            "station_gap_slope": ols_slope(frame["source"], frame["target"]),
            "network_slope": ols_slope(net["source"], net["target"]),
            "n_units": len(frame),
            "n_networks": len(net),
            "n_placements": len(frame),
        }.items():
            air2_panel_rows.append(
                {
                    "source_family": source_label,
                    "target_family": "4_xgboost",
                    "metric": key,
                    "value": value,
                }
            )
    pd.DataFrame(air2_panel_rows).to_csv(
        OUTPUT / "air2stream_panel_cells.csv", index=False
    )

    matrix = pd.DataFrame(matrix_rows)
    matrix.to_csv(OUTPUT / "matrix_long.csv", index=False)
    for metric in ("network_spearman", "station_gap_spearman", "station_gap_slope"):
        wide = matrix.loc[matrix["metric"].eq(metric)].pivot(
            index="source_family", columns="target_family", values="value"
        )
        wide.to_csv(OUTPUT / f"matrix_{metric}.csv")

    full_roster = full_roster_extension()
    full_roster.to_csv(OUTPUT / "matrix_extension_42networks.csv", index=False)

    print("== diagonal vs off-diagonal ==", flush=True)
    diagonal: list[dict[str, object]] = []
    off_diagonal: list[dict[str, object]] = []
    core = ["1_linear_pchip_boundary", "2_seasonal_boundary_ridge", "3_donor_covariance_ridge", "4_xgboost", "5_bilstm"]
    for row in matrix_rows:
        if row["metric"] not in ("network_spearman", "station_gap_spearman"):
            continue
        if row["value"] is None:
            continue
        source, target = row["source_family"], row["target_family"]
        if source not in core or target not in core:
            continue
        entry = {"level": row["metric"].replace("_spearman", ""), "value": row["value"], "cell": f"{source}|{target}"}
        if source == target:
            diagonal.append(entry)
        else:
            off_diagonal.append(entry)
    diagonal_frame = pd.DataFrame(diagonal)
    off_diagonal_frame = pd.DataFrame(off_diagonal)
    summary_rows = []
    for level in ("network", "station_gap"):
        diag = diagonal_frame.loc[diagonal_frame["level"].eq(level), "value"]
        off = off_diagonal_frame.loc[off_diagonal_frame["level"].eq(level), "value"]
        summary_rows.append(
            {
                "level": level,
                "diagonal_mean": float(np.mean(diag)) if len(diag) else None,
                "diagonal_median": float(np.median(diag)) if len(diag) else None,
                "diagonal_n": len(diag),
                "off_diagonal_mean": float(np.mean(off)) if len(off) else None,
                "off_diagonal_median": float(np.median(off)) if len(off) else None,
                "off_diagonal_n": len(off),
                "mean_gap": float(np.mean(diag) - np.mean(off)) if len(diag) and len(off) else None,
            }
        )
    pd.DataFrame(summary_rows).to_csv(OUTPUT / "diagonal_vs_offdiagonal.csv", index=False)
    diagonal_frame.to_csv(OUTPUT / "diagonal_cells.csv", index=False)
    off_diagonal_frame.to_csv(OUTPUT / "offdiagonal_cells.csv", index=False)

    print("== seed stability ==", flush=True)
    stability: list[dict[str, object]] = []
    seed_curves: dict[int, pd.DataFrame] = {}
    for seed in SEEDS:
        sub = neural_sources.loc[neural_sources["seed"].eq(seed)]
        seed_curves[seed] = curve_by_season(sub)
    for seed, curve in seed_curves.items():
        merged = seed_averaged.merge(
            curve,
            on=["network_id", "station_id", "gap_length", "season"],
            how="inner",
        )
        unit = merged.groupby(["network_id", "station_id", "gap_length"], as_index=False).agg(
            source=("source_mae", "mean"),
            target=("mae_deg_c", "mean"),
        )
        network = unit.groupby("network_id", as_index=False).mean(numeric_only=True)
        stability.append(
            {
                "seed": seed,
                "station_gap_spearman_vs_seed_average": spearman(unit, "source", "target"),
                "network_spearman_vs_seed_average": spearman(network, "source", "target"),
            }
        )
    for left, right in ((0, 1), (0, 2), (1, 2)):
        merged = seed_curves[left].merge(
            seed_curves[right],
            on=["network_id", "station_id", "gap_length", "season"],
            how="inner",
            suffixes=("_a", "_b"),
        )
        unit = merged.groupby(["network_id", "station_id", "gap_length"], as_index=False).agg(
            a=("source_mae_a", "mean"),
            b=("source_mae_b", "mean"),
        )
        stability.append(
            {
                "seed": f"pair_{left}_{right}",
                "station_gap_spearman_vs_seed_average": spearman(unit, "a", "b"),
                "network_spearman_vs_seed_average": None,
            }
        )
    pd.DataFrame(stability).to_csv(OUTPUT / "seed_stability.csv", index=False)

    print("== artifacts index ==", flush=True)
    artifacts = pd.DataFrame(
        [
            {"artifact": path.name, "path": str(path.relative_to(ROOT)), "rows": _row_count(path)}
            for path in sorted(OUTPUT.glob("*"))
            if path.is_file() and path.suffix in (".csv", ".json", ".png")
        ]
    )
    artifacts.to_csv(OUTPUT / "artifacts_index.csv", index=False)

    elapsed = time.time() - started
    (OUTPUT / "run_meta.json").write_text(
        json.dumps(
            {
                "script": str(Path(__file__).name),
                "networks": NETWORKS,
                "seeds": list(SEEDS),
                "fit_gaps": list(FIT_GAPS),
                "neural_gaps": list(NEURAL_GAPS),
                "placements_per_unit": PLACEMENTS_PER_UNIT,
                "neural_config": NEURAL_CONFIG,
                "elapsed_seconds": round(elapsed, 1),
            },
            indent=2,
        )
    )
    print(f"done in {elapsed / 60:.1f} min", flush=True)


def _row_count(path: Path) -> int:
    if path.suffix != ".csv":
        return 0
    try:
        return sum(1 for _ in path.open()) - 1
    except OSError:
        return 0


if __name__ == "__main__":
    main()
