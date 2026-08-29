#!/usr/bin/env python3
"""Mechanism-stratified missingness matrix on the daily-QC confirmation subset (agent a).

For each missingness mechanism we build a mechanism-specific empirical stress
curve from trial gaps planted inside the fitting years (nested chronological
split, XGBoost recovery pipeline identical to the paper: 300 trees, depth 4,
lr 0.05, boundary + donor features), inject the same mechanism into the
evaluation years, recover, and test network-level Spearman and equal-network
calibration of curve risk -> outer loss.  A mismatch experiment applies the
uniform-block curve to the other mechanisms' evaluation gaps.  Mechanism (e)
(drought / low-flow bias) is skipped: no discharge data exists for the
confirmation panel in data/processed.  Mechanism (g) uses the strongest donor
as the forcing covariate proxy because no air temperature exists in the panel.

Outputs (namespace only):
    results/revision_v12/t06_missingness_matrix/agent_a/
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    GAP_LENGTHS,
    XGBOOST_PARAMETERS,
    read_temperature_panel,
)

NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
OUTPUT = ROOT / "results/revision_v12/t06_missingness_matrix/agent_a"

NETWORKS = (
    "gkd_bayern_main",
    "huc8_17090004",
    "gkd_bayern_donau",
    "lubw_neckar",
    "foen_aare_aaregebiet",
    "huc8_17090001",
    "arso_sava",
    "huc8_05030103",
    "huc8_02040101",
    "arso_savinja",
    "gkd_bayern_isar",
    "huc8_02040104",
)

MAX_STATIONS_PER_NETWORK = 10
MIN_TRAIN_DAYS = 365
K_TRIAL = 12
K_EVAL = 20
SUMMER_START_DOY = (152, 273)  # Jun 1 .. Sep 30
BIAS_QUANTILE = 0.70
INTER_BLOCK_GAP_DAYS = 3
MECHANISMS = (
    "a_uniform_block",
    "b_multi_block",
    "c_summer_biased",
    "d_high_temperature_biased",
    "f_donor_synchronous",
    "g_target_plus_primary_covariate",
    "h_online_left_boundary",
)
SUPPORT_THRESHOLDS = {"spearman": 0.60, "slope_lo": 0.50, "slope_hi": 1.50}


def year_roster(index: pd.DatetimeIndex, fraction: float = 0.7) -> tuple[tuple[int, ...], tuple[int, ...]]:
    years = tuple(int(value) for value in sorted(pd.unique(index.year)))
    cut = min(len(years) - 1, max(1, round(len(years) * fraction)))
    return years[:cut], years[cut:]


def seasonal_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    phase = 2.0 * np.pi * (index.dayofyear.to_numpy(dtype=float) - 1.0) / np.where(
        index.is_leap_year, 366.0, 365.0
    )
    return pd.DataFrame(
        {
            "doy_sin_1": np.sin(phase),
            "doy_cos_1": np.cos(phase),
            "doy_sin_2": np.sin(2.0 * phase),
            "doy_cos_2": np.cos(2.0 * phase),
            "doy_sin_3": np.sin(3.0 * phase),
            "doy_cos_3": np.cos(3.0 * phase),
        },
        index=index,
    )


def select_even(candidates: np.ndarray, count: int) -> np.ndarray:
    """Evenly spaced deterministic selection (paper select_placements)."""
    if len(candidates) <= count:
        return candidates
    positions = np.linspace(0, len(candidates) - 1, num=count, dtype=int)
    return candidates[positions]


def block_pattern(length: int) -> tuple[tuple[int, int], ...]:
    """Offset/length pairs for the multi-block mechanism (3-day observed runs)."""
    if length < 14:
        return ((0, length),)
    n_blocks = max(2, min(int(np.ceil(length / 14.0)), 8))
    base = length // n_blocks
    remainder = length - base * n_blocks
    blocks = []
    position = 0
    for block_index in range(n_blocks):
        block_length = base + (1 if block_index < remainder else 0)
        blocks.append((position, block_length))
        position += block_length + INTER_BLOCK_GAP_DAYS
    return tuple(blocks)


def block_span(length: int) -> int:
    blocks = block_pattern(length)
    return blocks[-1][0] + blocks[-1][1]


def candidate_starts(
    panel: pd.DataFrame,
    target: str,
    donors: tuple[str, ...],
    period_mask: np.ndarray,
    span: int,
    *,
    require_donors: bool,
    require_right_boundary: bool = True,
) -> np.ndarray:
    n = len(panel)
    target_obs = panel[target].notna().to_numpy(dtype=bool)
    window = np.ones(span, dtype=int)
    ok = np.convolve(target_obs.astype(int), window, mode="valid") == span
    ok &= np.convolve(period_mask.astype(int), window, mode="valid") == span
    if require_donors and donors:
        donors_ok = panel[list(donors)].notna().all(axis=1).to_numpy(dtype=bool)
        ok &= np.convolve(donors_ok.astype(int), window, mode="valid") == span
    starts = np.arange(len(ok))
    bounded = (starts > 0) & (starts + span < n)
    bounded &= target_obs[np.maximum(starts - 1, 0)]
    if require_right_boundary:
        bounded &= target_obs[np.minimum(starts + span, n - 1)]
    return starts[ok & bounded]


def day_of_year_climatology(target: pd.Series, fit_mask: np.ndarray) -> np.ndarray:
    training = pd.DataFrame(
        {"day": target.index.dayofyear, "value": target.to_numpy(dtype=float)}
    ).loc[fit_mask & target.notna().to_numpy(dtype=bool)]
    if len(training) == 0:
        return np.full(366, float("nan"))
    day_values = training.groupby("day")["value"].median()
    fallback = float(training["value"].median())
    return day_values.reindex(range(1, 367)).fillna(fallback).to_numpy(dtype=float)


def anomaly_correlation(target: pd.Series, donor: pd.Series, fit_mask: np.ndarray) -> float:
    t_clim = day_of_year_climatology(target, fit_mask)
    d_clim = day_of_year_climatology(donor, fit_mask)
    t_anom = target.to_numpy(dtype=float) - t_clim[target.index.dayofyear.to_numpy() - 1]
    d_anom = donor.to_numpy(dtype=float) - d_clim[donor.index.dayofyear.to_numpy() - 1]
    valid = fit_mask & np.isfinite(t_anom) & np.isfinite(d_anom)
    if int(valid.sum()) < 2:
        return float("nan")
    return float(np.corrcoef(t_anom[valid], d_anom[valid])[0, 1])


def fit_model(
    panel: pd.DataFrame,
    target: str,
    donors: tuple[str, ...],
    fit_mask: np.ndarray,
    *,
    left_only: bool,
    xgb_parameters: dict,
) -> XGBRegressor | None:
    target_train = panel[target].where(fit_mask)
    boundary = target_train.shift(1) if left_only else (
        target_train.shift(1) + target_train.shift(-1)
    ) / 2.0
    frame = seasonal_features(panel.index)
    frame["B__boundary_temperature"] = boundary
    for donor in donors:
        frame[f"D__{donor}"] = panel[donor]
    fitting = fit_mask & panel[target].notna().to_numpy(dtype=bool)
    if int(fitting.sum()) < MIN_TRAIN_DAYS:
        return None
    model = XGBRegressor(**dict(xgb_parameters))
    model.fit(frame.loc[fitting], panel.loc[fitting, target])
    return model


def boundary_values(target: pd.Series, left_idx: int, right_idx: int, n_days: int) -> np.ndarray:
    left = float(target.iloc[left_idx])
    right = float(target.iloc[right_idx])
    fraction = np.arange(1, n_days + 1, dtype=float) / (n_days + 1.0)
    return left + fraction * (right - left)


def score_gap(
    panel: pd.DataFrame,
    model: XGBRegressor,
    target: str,
    donors: tuple[str, ...],
    start: int,
    span: int,
    *,
    mechanism: str,
    best_donor: str | None,
    left_only: bool,
    blocks: tuple[tuple[int, int], ...] | None = None,
) -> float:
    if mechanism == "b_multi_block":
        masked = np.concatenate(
            [np.arange(start + offset, start + offset + length) for offset, length in blocks]
        )
        boundary = np.concatenate(
            [
                boundary_values(panel[target], start + offset - 1, start + offset + length, length)
                for offset, length in blocks
            ]
        )
    else:
        masked = np.arange(start, start + span)
        if left_only:
            boundary = np.full(span, float(panel[target].iloc[start - 1]))
        else:
            boundary = boundary_values(panel[target], start - 1, start + span, span)
    frame = seasonal_features(panel.index[masked])
    frame["B__boundary_temperature"] = boundary
    for donor in donors:
        values = panel[donor].to_numpy(dtype=float)
        if mechanism == "f_donor_synchronous":
            values = values.copy()
            values[masked] = np.nan
        elif mechanism == "g_target_plus_primary_covariate" and donor == best_donor:
            values = values.copy()
            values[masked] = np.nan
        frame[f"D__{donor}"] = values[masked]
    prediction = model.predict(frame)
    truth = panel[target].to_numpy(dtype=float)[masked]
    return float(np.mean(np.abs(prediction - truth)))


def _select_starts(
    starts: np.ndarray,
    count: int,
    *,
    mechanism: str,
    day_of_year: np.ndarray,
    bias_scores: np.ndarray | None,
) -> np.ndarray:
    if mechanism == "c_summer_biased":
        lo, hi = SUMMER_START_DOY
        season = (day_of_year[starts] >= lo) & (day_of_year[starts] <= hi)
        starts = starts[season]
    elif mechanism == "d_high_temperature_biased":
        if len(starts) and bias_scores is not None:
            threshold = float(np.quantile(bias_scores[starts], BIAS_QUANTILE))
            top = starts[bias_scores[starts] >= threshold]
            order = np.argsort(-bias_scores[top], kind="stable")
            starts = top[order]
    return select_even(starts, count)


def process_network(
    network_id: str,
    panel: pd.DataFrame,
    xgb_parameters: dict,
) -> dict:
    panel = panel.copy().sort_index()
    panel.index.name = "date"
    panel.columns = panel.columns.astype(str)
    daily_index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(daily_index)
    panel.index.name = "date"
    train_years, evaluation_years = year_roster(panel.index, fraction=0.7)
    fitting_index = panel.index[panel.index.year.isin(train_years)]
    fit_years, trial_years = year_roster(fitting_index, fraction=0.7)
    fit_mask = np.asarray(panel.index.year.isin(fit_years), dtype=bool)
    trial_mask = np.asarray(panel.index.year.isin(trial_years), dtype=bool)
    eval_mask = np.asarray(panel.index.year.isin(evaluation_years), dtype=bool)
    fitting_mask = fit_mask | trial_mask
    day_of_year = panel.index.dayofyear.to_numpy(dtype=int)

    station_records = []
    for station in panel.columns:
        paired = int(
            (
                fitting_mask
                & panel[station].notna().to_numpy(dtype=bool)
                & panel[panel.columns.difference([station])].notna().any(axis=1).to_numpy(dtype=bool)
            ).sum()
        )
        train_days = int((fit_mask & panel[station].notna().to_numpy(dtype=bool)).sum())
        station_records.append(
            {
                "station_id": station,
                "train_days_fit_years": train_days,
                "paired_days_fitting_years": paired,
            }
        )
    station_records = sorted(
        station_records, key=lambda row: row["train_days_fit_years"], reverse=True
    )[:MAX_STATIONS_PER_NETWORK]

    curves: dict[str, dict] = {}
    units: list[dict] = []
    per_station: dict[str, dict] = {}
    skipped = []

    for record in station_records:
        target = record["station_id"]
        donor_candidates = tuple(
            str(column)
            for column in panel.columns
            if str(column) != target
        )
        donors = tuple(
            donor
            for donor in donor_candidates
            if int(
                (
                    fitting_mask
                    & panel[target].notna().to_numpy(dtype=bool)
                    & panel[donor].notna().to_numpy(dtype=bool)
                ).sum()
            )
            >= MIN_TRAIN_DAYS
        )
        train_days = int((fit_mask & panel[target].notna().to_numpy(dtype=bool)).sum())
        if train_days < MIN_TRAIN_DAYS or not donors:
            skipped.append(
                {
                    "network_id": network_id,
                    "station_id": target,
                    "reason": "insufficient_training" if train_days < MIN_TRAIN_DAYS else "no_donor",
                    "train_days_fit_years": train_days,
                    "n_donors": len(donors),
                }
            )
            continue
        model_symmetric = fit_model(panel, target, donors, fit_mask, left_only=False, xgb_parameters=xgb_parameters)
        model_left = fit_model(panel, target, donors, fit_mask, left_only=True, xgb_parameters=xgb_parameters)
        if model_symmetric is None or model_left is None:
            skipped.append(
                {
                    "network_id": network_id,
                    "station_id": target,
                    "reason": "model_fit_failed",
                    "train_days_fit_years": train_days,
                    "n_donors": len(donors),
                }
            )
            continue
        climatology = day_of_year_climatology(panel[target], fit_mask)
        climatology = np.where(np.isfinite(climatology), climatology, np.nanmedian(climatology))
        donor_correlations = {
            donor: anomaly_correlation(panel[target], panel[donor], fit_mask) for donor in donors
        }
        best_donor = max(
            (donor for donor in donors if np.isfinite(donor_correlations[donor])),
            key=donor_correlations.__getitem__,
            default=donors[0],
        )
        for donor in donors:
            if not np.isfinite(donor_correlations[donor]):
                donor_correlations[donor] = 0.0
        cumulative_clim = np.concatenate([[0.0], np.cumsum(climatology[day_of_year - 1])])

        per_station[target] = {
            "model_symmetric": model_symmetric,
            "model_left": model_left,
            "donors": donors,
            "best_donor": best_donor,
            "donor_correlations": donor_correlations,
            "climatology": climatology,
            "cumulative_clim": cumulative_clim,
        }

    for target, state in per_station.items():
        donors = state["donors"]
        best_donor = state["best_donor"]
        model_symmetric = state["model_symmetric"]
        model_left = state["model_left"]
        donors_excluding_best = tuple(d for d in donors if d != best_donor)

        for mechanism in MECHANISMS:
            trial_by_length: dict[int, list[float]] = {int(length): [] for length in GAP_LENGTHS}
            for length in GAP_LENGTHS:
                length = int(length)
                span = block_span(length) if mechanism == "b_multi_block" else length
                blocks = block_pattern(length) if mechanism == "b_multi_block" else None
                require_donors = mechanism not in ("f_donor_synchronous",)
                required_donors = donors if require_donors else ()
                if mechanism == "g_target_plus_primary_covariate":
                    required_donors = donors_excluding_best
                starts = candidate_starts(
                    panel,
                    target,
                    required_donors,
                    trial_mask,
                    span,
                    require_donors=bool(required_donors),
                )
                bias_scores = None
                if mechanism == "d_high_temperature_biased" and len(starts):
                    bias_scores = np.full(len(panel), np.nan)
                    bias_scores[starts] = (
                        state["cumulative_clim"][starts + span] - state["cumulative_clim"][starts]
                    ) / span
                selected = _select_starts(
                    starts, K_TRIAL, mechanism=mechanism, day_of_year=day_of_year, bias_scores=bias_scores
                )
                model = model_left if mechanism == "h_online_left_boundary" else model_symmetric
                for start in selected:
                    mae = score_gap(
                        panel,
                        model,
                        target,
                        donors,
                        int(start),
                        span,
                        mechanism=mechanism,
                        best_donor=best_donor,
                        left_only=mechanism == "h_online_left_boundary",
                        blocks=blocks,
                    )
                    trial_by_length[length].append(mae)
            trial_mean = {
                int(length): float(np.mean(values)) if values else float("nan")
                for length, values in trial_by_length.items()
            }
            trial_n = {int(length): len(values) for length, values in trial_by_length.items()}
            all_trial = [
                mae for values in trial_by_length.values() for mae in values
            ]
            network_mean = float(np.mean(all_trial)) if all_trial else float("nan")
            curves.setdefault(mechanism, {})[target] = {
                "trial_mean": trial_mean,
                "trial_n": trial_n,
                "network_mean": network_mean,
            }
            for length in GAP_LENGTHS:
                length = int(length)
                span = block_span(length) if mechanism == "b_multi_block" else length
                blocks = block_pattern(length) if mechanism == "b_multi_block" else None
                require_donors = mechanism not in ("f_donor_synchronous",)
                required_donors = donors if require_donors else ()
                if mechanism == "g_target_plus_primary_covariate":
                    required_donors = donors_excluding_best
                starts = candidate_starts(
                    panel,
                    target,
                    required_donors,
                    eval_mask,
                    span,
                    require_donors=bool(required_donors),
                )
                bias_scores = None
                if mechanism == "d_high_temperature_biased" and len(starts):
                    bias_scores = np.full(len(panel), np.nan)
                    bias_scores[starts] = (
                        state["cumulative_clim"][starts + span] - state["cumulative_clim"][starts]
                    ) / span
                selected = _select_starts(
                    starts, K_EVAL, mechanism=mechanism, day_of_year=day_of_year, bias_scores=bias_scores
                )
                model = model_left if mechanism == "h_online_left_boundary" else model_symmetric
                for start in selected:
                    mae = score_gap(
                        panel,
                        model,
                        target,
                        donors,
                        int(start),
                        span,
                        mechanism=mechanism,
                        best_donor=best_donor,
                        left_only=mechanism == "h_online_left_boundary",
                        blocks=blocks,
                    )
                    units.append(
                        {
                            "network_id": network_id,
                            "station_id": target,
                            "gap_length": length,
                            "placement": len(units),
                            "mechanism": mechanism,
                            "gap_start": str(panel.index[int(start)].date()),
                            "observed_recovery_loss": mae,
                        }
                    )

    return {
        "network_id": network_id,
        "curves": curves,
        "units": units,
        "per_station": per_station,
        "skipped": skipped,
        "train_years": train_years,
        "evaluation_years": evaluation_years,
        "fit_years": fit_years,
        "trial_years": trial_years,
    }


def fallback_lookup(
    curves: dict[str, dict],
    network_id: str,
    station: str,
    length: int,
) -> tuple[float, str]:
    if station in curves and np.isfinite(curves[station]["trial_mean"][length]):
        return float(curves[station]["trial_mean"][length]), "station_horizon"
    horizon_values = [
        curves[other]["trial_mean"][length]
        for other in curves
        if np.isfinite(curves[other]["trial_mean"][length])
    ]
    if horizon_values:
        return float(np.mean(horizon_values)), "network_horizon"
    network_values = [
        value
        for other in curves
        for value in curves[other]["trial_mean"].values()
        if np.isfinite(value)
    ]
    if network_values:
        return float(np.mean(network_values)), "network_mean"
    return float("nan"), "none"


def station_gap_units(units: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(units)
    return (
        frame.groupby(["network_id", "station_id", "gap_length", "mechanism"], as_index=False)
        .agg(observed_recovery_loss=("observed_recovery_loss", "mean"), n_placements=("placement", "size"))
    )


def network_metrics(frame: pd.DataFrame) -> dict:
    observed = frame["observed_recovery_loss"].to_numpy(dtype=float)
    predicted = frame["predicted_loss"].to_numpy(dtype=float)
    counts = frame.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(frame)), predicted])
    intercept, slope = np.linalg.lstsq(design * root_weight[:, None], observed * root_weight, rcond=None)[0]
    network = frame.groupby("network_id")[["predicted_loss", "observed_recovery_loss"]].mean()
    network_spearman = (
        spearmanr(network["predicted_loss"], network["observed_recovery_loss"])
        if len(network) >= 3
        else (float("nan"), float("nan"))
    )
    pooled_spearman = spearmanr(predicted, observed)
    four_horizon = frame.loc[frame["gap_length"].isin((7, 30, 90, 180))]
    if len(four_horizon) >= 12 and four_horizon["network_id"].nunique() >= 3:
        four_network = four_horizon.groupby("network_id")[
            ["predicted_loss", "observed_recovery_loss"]
        ].mean()
        four_horizon_spearman = float(
            spearmanr(four_network["predicted_loss"], four_network["observed_recovery_loss"]).statistic
        )
    else:
        four_horizon_spearman = float("nan")
    return {
        "network_spearman": float(network_spearman[0]) if len(network) >= 3 else float("nan"),
        "network_spearman_p": float(network_spearman[1]) if len(network) >= 3 else float("nan"),
        "pooled_spearman": float(pooled_spearman[0]),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "mean_predicted_loss": float(np.mean(predicted)),
        "mean_observed_loss": float(np.mean(observed)),
        "n_units": len(frame),
        "n_networks": int(frame["network_id"].nunique()),
        "network_spearman_4horizon": four_horizon_spearman,
        "n_units_4horizon": int(len(four_horizon)),
    }


def main() -> None:
    start_time = time.time()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    xgb_parameters = {**XGBOOST_PARAMETERS, "n_jobs": 8}
    all_units: list[dict] = []
    all_curves: dict[str, dict[str, dict]] = {}
    all_skipped: list[dict] = []
    network_records = []

    for network_id in NETWORKS:
        t0 = time.time()
        panel = read_temperature_panel(str(NETWORK_ROOT / network_id / "daily_wide_temperature.csv"))
        result = process_network(network_id, panel, xgb_parameters)
        all_units.extend(result["units"])
        for mechanism, station_curves in result["curves"].items():
            all_curves.setdefault(mechanism, {})[network_id] = station_curves
        all_skipped.extend(result["skipped"])
        network_records.append(
            {
                "network_id": network_id,
                "n_stations_scored": len(result["per_station"]),
                "n_stations_skipped": len(result["skipped"]),
                "train_years": "|".join(map(str, result["train_years"])),
                "fit_years": "|".join(map(str, result["fit_years"])),
                "trial_years": "|".join(map(str, result["trial_years"])),
                "evaluation_years": "|".join(map(str, result["evaluation_years"])),
                "seconds": round(time.time() - t0, 1),
            }
        )
        print(
            f"{network_id}: scored {len(result['per_station'])} stations, "
            f"{len(result['units'])} placements, {round(time.time() - t0, 1)} s",
            flush=True,
        )

    raw_units = pd.DataFrame(all_units)
    raw_units.to_csv(OUTPUT / "placement_losses.csv", index=False)
    grouped = station_gap_units(all_units)
    grouped.to_csv(OUTPUT / "station_gap_units.csv", index=False)

    curve_rows = []
    for mechanism, networks in all_curves.items():
        for network_id, stations in networks.items():
            for station, state in stations.items():
                for length in GAP_LENGTHS:
                    curve_rows.append(
                        {
                            "mechanism": mechanism,
                            "network_id": network_id,
                            "station_id": station,
                            "gap_length": int(length),
                            "trial_mean_mae_deg_c": state["trial_mean"][int(length)],
                            "n_trial_placements": state["trial_n"][int(length)],
                            "network_trial_mean_mae_deg_c": state["network_mean"],
                        }
                    )
    pd.DataFrame(curve_rows).to_csv(OUTPUT / "mechanism_curves.csv", index=False)
    pd.DataFrame(network_records).to_csv(OUTPUT / "network_panel.csv", index=False)
    pd.DataFrame(all_skipped).to_csv(OUTPUT / "station_attrition.csv", index=False)

    metric_rows = []
    unit_rows = []
    for mechanism in MECHANISMS:
        mechanism_units = grouped.loc[grouped["mechanism"].eq(mechanism)].copy()
        mechanism_units["predicted_loss"] = [
            fallback_lookup(all_curves[mechanism][network], network, station, length)[0]
            for network, station, length in zip(
                mechanism_units["network_id"],
                mechanism_units["station_id"],
                mechanism_units["gap_length"],
            )
        ]
        mechanism_units["fallback_type"] = [
            fallback_lookup(all_curves[mechanism][network], network, station, length)[1]
            for network, station, length in zip(
                mechanism_units["network_id"],
                mechanism_units["station_id"],
                mechanism_units["gap_length"],
            )
        ]
        mechanism_units = mechanism_units.loc[
            np.isfinite(mechanism_units["predicted_loss"])
            & np.isfinite(mechanism_units["observed_recovery_loss"])
        ].copy()
        mechanism_units["mechanism"] = mechanism
        unit_rows.append(mechanism_units)
        metric_rows.append(
            {
                "mechanism": mechanism,
                "matched": True,
                **network_metrics(mechanism_units),
                "fallback_fraction": float(
                    mechanism_units["fallback_type"].ne("station_horizon").mean()
                ),
                "station_horizon_units": int(mechanism_units["fallback_type"].eq("station_horizon").sum()),
            }
        )
        print(
            f"{mechanism}: matched network spearman "
            f"{metric_rows[-1]['network_spearman']:.3f}, slope {metric_rows[-1]['calibration_slope']:.3f}, "
            f"{metric_rows[-1]['n_units']} units",
            flush=True,
        )

    mismatch_rows = []
    for mechanism in MECHANISMS:
        if mechanism == "a_uniform_block":
            continue
        mechanism_units = grouped.loc[grouped["mechanism"].eq(mechanism)].copy()
        mechanism_units["predicted_loss"] = [
            fallback_lookup(all_curves["a_uniform_block"][network], network, station, length)[0]
            for network, station, length in zip(
                mechanism_units["network_id"],
                mechanism_units["station_id"],
                mechanism_units["gap_length"],
            )
        ]
        mechanism_units = mechanism_units.loc[
            np.isfinite(mechanism_units["predicted_loss"])
            & np.isfinite(mechanism_units["observed_recovery_loss"])
        ].copy()
        mismatch_rows.append(
            {
                "mechanism": mechanism,
                "matched": False,
                "curve_source": "a_uniform_block",
                **network_metrics(mechanism_units),
            }
        )
    uniform_units = grouped.loc[grouped["mechanism"].eq("a_uniform_block")].copy()
    uniform_units["predicted_loss"] = [
        fallback_lookup(all_curves["c_summer_biased"][network], network, station, length)[0]
        for network, station, length in zip(
            uniform_units["network_id"],
            uniform_units["station_id"],
            uniform_units["gap_length"],
        )
    ]
    uniform_units = uniform_units.loc[
        np.isfinite(uniform_units["predicted_loss"])
        & np.isfinite(uniform_units["observed_recovery_loss"])
    ].copy()
    mismatch_rows.append(
        {
            "mechanism": "a_uniform_block",
            "matched": False,
            "curve_source": "c_summer_biased",
            **network_metrics(uniform_units),
        }
    )
    mismatch = pd.DataFrame(mismatch_rows)
    mismatch.to_csv(OUTPUT / "mismatch_metrics.csv", index=False)

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(OUTPUT / "mechanism_metrics.csv", index=False)
    matched_metrics = metrics.set_index("mechanism")
    pd.concat(unit_rows, ignore_index=True).to_csv(OUTPUT / "mechanism_units.csv", index=False)

    support_rows = []
    for mechanism in MECHANISMS:
        structure = {
            "a_uniform_block": "single contiguous block",
            "b_multi_block": "repeated short blocks (3-day observed runs)",
            "c_summer_biased": "single block, start in Jun-Sep",
            "d_high_temperature_biased": "single block on high-climatology windows",
            "f_donor_synchronous": "single block, target + all donors masked",
            "g_target_plus_primary_covariate": "single block, target + strongest donor masked",
            "h_online_left_boundary": "single block, right boundary hidden (online)",
        }[mechanism]
        boundary_support = {
            "a_uniform_block": "left+right",
            "b_multi_block": "left+right per block",
            "c_summer_biased": "left+right",
            "d_high_temperature_biased": "left+right",
            "f_donor_synchronous": "left+right",
            "g_target_plus_primary_covariate": "left+right",
            "h_online_left_boundary": "left only",
        }[mechanism]
        donor_support = {
            "a_uniform_block": "all donors",
            "b_multi_block": "all donors",
            "c_summer_biased": "all donors",
            "d_high_temperature_biased": "all donors",
            "f_donor_synchronous": "none (all masked)",
            "g_target_plus_primary_covariate": "weaker donors only",
            "h_online_left_boundary": "all donors",
        }[mechanism]
        seasonal_bias = {
            "a_uniform_block": "none",
            "b_multi_block": "none",
            "c_summer_biased": "summer start",
            "d_high_temperature_biased": "high-temperature windows",
            "f_donor_synchronous": "none",
            "g_target_plus_primary_covariate": "none",
            "h_online_left_boundary": "none",
        }[mechanism]
        row = matched_metrics.loc[mechanism].to_dict()
        uniform_row = mismatch.loc[
            mismatch["mechanism"].eq(mechanism) & mismatch["curve_source"].eq("a_uniform_block")
        ]
        uniform_row = uniform_row.iloc[0].to_dict() if len(uniform_row) else {}
        spearman = float(row["network_spearman"])
        slope = float(row["calibration_slope"])
        if spearman >= SUPPORT_THRESHOLDS["spearman"] and SUPPORT_THRESHOLDS["slope_lo"] <= slope <= SUPPORT_THRESHOLDS["slope_hi"]:
            supported = "supported"
        elif spearman >= SUPPORT_THRESHOLDS["spearman"]:
            supported = "partial_magnitude_mismatch"
        else:
            supported = "not_supported"
        support_rows.append(
            {
                "mechanism": mechanism,
                "structure": structure,
                "seasonal_bias": seasonal_bias,
                "boundary_support": boundary_support,
                "donor_support": donor_support,
                "matched_network_spearman": spearman,
                "matched_calibration_slope": slope,
                "matched_n_units": int(row["n_units"]),
                "matched_fallback_fraction": float(row["fallback_fraction"]),
                "uniform_curve_network_spearman": float(uniform_row.get("network_spearman", np.nan)),
                "uniform_curve_calibration_slope": float(uniform_row.get("calibration_slope", np.nan)),
                "supported_by_matched_fitting_curve": supported,
            }
        )
    support = pd.DataFrame(support_rows)
    support.to_csv(OUTPUT / "support_matrix.csv", index=False)

    manifest = {
        "analysis": "revision_v12_t06_missingness_matrix_agent_a",
        "script": "scripts/rev_v12_t06_missingness_a.py",
        "pipeline": {
            "model": "xgboost",
            "n_estimators": XGBOOST_PARAMETERS["n_estimators"],
            "max_depth": XGBOOST_PARAMETERS["max_depth"],
            "learning_rate": XGBOOST_PARAMETERS["learning_rate"],
            "features": ["boundary", "donors", "seasonal harmonics"],
            "outer_split_fraction": 0.7,
            "inner_split_fraction": 0.7,
            "trial_placements_per_gap": K_TRIAL,
            "evaluation_placements_per_gap": K_EVAL,
            "min_train_days": MIN_TRAIN_DAYS,
            "gap_lengths": list(GAP_LENGTHS),
            "summer_start_doy": list(SUMMER_START_DOY),
            "high_temperature_bias_quantile": BIAS_QUANTILE,
            "support_thresholds": SUPPORT_THRESHOLDS,
        },
        "mechanisms": list(MECHANISMS),
        "mechanism_e_skipped_reason": (
            "no discharge (F/L) data for confirmation-panel networks in data/processed"
        ),
        "mechanism_g_note": (
            "no air temperature in confirmation panels; strongest donor used as forcing proxy"
        ),
        "networks": [{"network_id": row["network_id"], **row} for row in network_records],
        "n_networks": len(network_records),
        "n_placements": len(all_units),
        "n_stations_skipped": len(all_skipped),
        "wall_seconds": round(time.time() - start_time, 1),
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
    print(f"done in {manifest['wall_seconds']} s", flush=True)


if __name__ == "__main__":
    main()
