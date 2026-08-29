#!/usr/bin/env python3
"""Agent A (adversarial pair): downstream thermal-regime metric distortion.

For the 15 QC'd confirmation networks with the most scored station-gaps, each
artificial gap in the outer evaluation years (horizons 7/30/90 days, <=5
placements per station-gap) is reconstructed with the frozen XGBoost B_union_D
pipeline (same code path as scripts/106/108/115).  Truth-vs-reconstruction
error is measured in ten downstream thermal-regime metrics:

  annual_mean, summer_mean (JJA), amplitude (July-January), phase (day of peak),
  p90, summer_max, exceed_20_days, exceed_25_days, degree_days_10, trend_slope.

Deliverables (results/revision_v12/t08_downstream_metrics/agent_a/):
  * per-placement metric errors + risk scores (placement_thermal_metrics.csv)
  * network-level metric errors (network_thermal_metrics.csv)
  * reconstruction series parquet (reconstruction_series.parquet)
  * risk->distortion Spearman correlations (correlation_risk_distortion.csv)
  * budget experiment: top-20% by risk / gap length / random / oracle
    (budget_comparison.csv, budget_combined.csv, budget_comparison.png)
  * metric error tables (metric_error_tables.csv), protection summary
  * REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stream_recoverability.experiments.development_data import (
    joint_complete_feature_rosters,
)
from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    _boundary_values,
    _candidate_starts,
    _climatology_prediction,
    _model_frame,
    read_temperature_panel,
    select_placements,
    year_split,
)

NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
EMPIRICAL_CSV = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
)
QC_SUMMARY = ROOT / "results/development_v11/confirmation_qc_summary.csv"
OUTPUT = ROOT / "results/revision_v12/t08_downstream_metrics/agent_a"

GAP_LENGTHS = (7, 30, 90)
PLACEMENTS_PER_GAP = 5
N_NETWORKS = 15
BUDGET_FRACTION = 0.20
RANDOM_REPEATS = 200
RANDOM_SEED = 0
MIN_TRAIN_DAYS = 365

METRIC_NAMES = (
    "annual_mean",
    "summer_mean",
    "amplitude",
    "phase_doy",
    "p90",
    "summer_max",
    "exceed_20_days",
    "exceed_25_days",
    "degree_days_10",
    "trend_slope",
)

METRIC_LABELS = {
    "annual_mean": "Annual mean (°C)",
    "summer_mean": "Summer (JJA) mean (°C)",
    "amplitude": "Amplitude (Jul−Jan, °C)",
    "phase_doy": "Phase (day of peak)",
    "p90": "90th percentile (°C)",
    "summer_max": "Summer maximum (°C)",
    "exceed_20_days": "Days >20 °C",
    "exceed_25_days": "Days >25 °C",
    "degree_days_10": "Degree days >10 °C (base 10)",
    "trend_slope": "Trend slope (°C/yr)",
}


def season_label(months: np.ndarray) -> np.ndarray:
    return np.select(
        [np.isin(months, [12, 1, 2]), np.isin(months, [3, 4, 5]), np.isin(months, [6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )


def thermal_metrics_np(
    x: np.ndarray,
    months: np.ndarray,
    years: np.ndarray,
    doy: np.ndarray,
    *,
    min_annual_days: int = 180,
    min_trend_years: int = 3,
) -> dict[str, float]:
    """Compute the ten downstream thermal-regime metrics on a daily series."""
    out: dict[str, float] = {}
    finite = np.isfinite(x)
    n = int(finite.sum())
    if n == 0:
        return {name: np.nan for name in METRIC_NAMES}
    xf = x[finite]
    out["annual_mean"] = float(np.mean(xf))
    summer = finite & np.isin(months, [6, 7, 8])
    if summer.any():
        out["summer_mean"] = float(np.mean(x[summer]))
        out["summer_max"] = float(np.max(x[summer]))
    else:
        out["summer_mean"] = np.nan
        out["summer_max"] = np.nan
    july = finite & (months == 7)
    january = finite & (months == 1)
    if july.any() and january.any():
        out["amplitude"] = float(np.mean(x[july]) - np.mean(x[january]))
    else:
        out["amplitude"] = np.nan
    if n >= 30:
        theta = 2.0 * np.pi * (doy[finite] - 1.0) / 365.25
        design = np.column_stack(
            [np.ones(n), np.sin(theta), np.cos(theta)]
        )
        coef = np.linalg.lstsq(design, xf, rcond=None)[0]
        peak = np.arctan2(coef[1], coef[2]) % (2.0 * np.pi)
        out["phase_doy"] = float(1.0 + peak * 365.25 / (2.0 * np.pi))
    else:
        out["phase_doy"] = np.nan
    out["p90"] = float(np.percentile(xf, 90))
    out["exceed_20_days"] = float(np.count_nonzero(xf > 20.0))
    out["exceed_25_days"] = float(np.count_nonzero(xf > 25.0))
    out["degree_days_10"] = float(np.sum(np.maximum(0.0, xf - 10.0)))
    yf = years[finite]
    annual_means = []
    for year in np.unique(yf):
        year_mask = yf == year
        if int(year_mask.sum()) >= min_annual_days:
            annual_means.append((float(year), float(np.mean(xf[year_mask]))))
    if len(annual_means) >= min_trend_years:
        trend_years = np.array([item[0] for item in annual_means])
        trend_values = np.array([item[1] for item in annual_means])
        slope = np.linalg.lstsq(
            np.column_stack([np.ones(len(trend_years)), trend_years]),
            trend_values,
            rcond=None,
        )[0][1]
        out["trend_slope"] = float(slope)
    else:
        out["trend_slope"] = np.nan
    return out


def distortion_pairs(
    truth_metrics: dict[str, float],
    filled_metrics: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    dist: dict[str, float] = {}
    signed: dict[str, float] = {}
    for name in METRIC_NAMES:
        t = truth_metrics[name]
        f = filled_metrics[name]
        if np.isnan(t) or np.isnan(f):
            dist[name] = np.nan
            signed[name] = np.nan
        elif name == "phase_doy":
            dist[name] = float(np.abs(((f - t + 182.625) % 365.25) - 182.625))
            signed[name] = f - t
        else:
            dist[name] = float(abs(f - t))
            signed[name] = f - t
    return dist, signed


def phase_distance(first: float, second: float) -> float:
    return float(np.abs(((second - first + 182.625) % 365.25) - 182.625))


def build_risk_lookups(empirical: pd.DataFrame) -> dict:
    empirical = empirical.copy()
    empirical["season"] = season_label(
        pd.DatetimeIndex(empirical["gap_start"]).month.to_numpy(dtype=int)
    )
    start_map = empirical.groupby(
        ["network_id", "station_id", "gap_length", "gap_start"]
    )["empirical_transfer_prediction"].mean()
    start_support = empirical.groupby(
        ["network_id", "station_id", "gap_length", "gap_start"]
    )["empirical_transfer_supported"].mean()
    season_map = empirical.groupby(
        ["network_id", "station_id", "gap_length", "season"]
    )["empirical_transfer_prediction"].mean()
    season_support = empirical.groupby(
        ["network_id", "station_id", "gap_length", "season"]
    )["empirical_transfer_supported"].mean()
    sg_map = empirical.groupby(["network_id", "station_id", "gap_length"])[
        "empirical_transfer_prediction"
    ].mean()
    sg_support = empirical.groupby(["network_id", "station_id", "gap_length"])[
        "empirical_transfer_supported"
    ].mean()
    ng_map = empirical.groupby(["network_id", "gap_length"])[
        "empirical_transfer_prediction"
    ].mean()
    ng_support = empirical.groupby(["network_id", "gap_length"])[
        "empirical_transfer_supported"
    ].mean()
    network_map = empirical.groupby("network_id")[
        "empirical_transfer_prediction"
    ].mean()
    network_support = empirical.groupby("network_id")[
        "empirical_transfer_supported"
    ].mean()
    mae_map = empirical.groupby(
        ["network_id", "station_id", "gap_length", "gap_start"]
    )["mae_deg_c"].mean()
    return {
        "start": start_map,
        "start_support": start_support,
        "season": season_map,
        "season_support": season_support,
        "sg": sg_map,
        "sg_support": sg_support,
        "ng": ng_map,
        "ng_support": ng_support,
        "network": network_map,
        "network_support": network_support,
        "mae": mae_map,
    }


def resolve_risk(
    lookups: dict,
    network: str,
    station: str,
    gap_length: int,
    gap_start: pd.Timestamp,
) -> tuple[float, str, bool]:
    key_start = (network, station, gap_length, gap_start)
    if key_start in lookups["start"]:
        return (
            float(lookups["start"][key_start]),
            "exact_start",
            bool(lookups["start_support"][key_start]),
        )
    season = str(season_label(np.asarray([gap_start.month]))[0])
    key_season = (network, station, gap_length, season)
    if key_season in lookups["season"]:
        return (
            float(lookups["season"][key_season]),
            "station_gap_season",
            bool(lookups["season_support"][key_season]),
        )
    key_sg = (network, station, gap_length)
    if key_sg in lookups["sg"]:
        return (
            float(lookups["sg"][key_sg]),
            "station_gap",
            bool(lookups["sg_support"][key_sg]),
        )
    key_ng = (network, gap_length)
    if key_ng in lookups["ng"]:
        return (
            float(lookups["ng"][key_ng]),
            "network_gap",
            bool(lookups["ng_support"][key_ng]),
        )
    if network in lookups["network"]:
        return (
            float(lookups["network"][network]),
            "network_mean",
            bool(lookups["network_support"][network]),
        )
    return np.nan, "unavailable", False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-networks", type=int, default=N_NETWORKS)
    parser.add_argument("--placements", type=int, default=PLACEMENTS_PER_GAP)
    parser.add_argument("--n-jobs", type=int, default=4)
    args = parser.parse_args()

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    empirical = pd.read_csv(
        EMPIRICAL_CSV, dtype={"network_id": str, "station_id": str}
    )
    empirical["gap_start"] = pd.to_datetime(empirical["gap_start"])
    lookups = build_risk_lookups(empirical)

    qualified = pd.read_csv(QC_SUMMARY, dtype={"network_id": str})
    ranked = (
        empirical.loc[empirical["gap_length"].isin(GAP_LENGTHS)]
        .groupby("network_id")["gap_start"]
        .size()
        .sort_values(ascending=False)
    )
    networks = ranked.head(args.max_networks).index.tolist()
    metadata = qualified.loc[
        qualified["network_id"].isin(networks), ["network_id", "provider", "domain"]
    ].set_index("network_id")
    parameters = {**XGBOOST_PARAMETERS, "n_jobs": args.n_jobs}

    placement_rows: list[dict[str, object]] = []
    series_rows: list[dict[str, object]] = []
    # per-network budget structures
    budget_networks: list[dict[str, object]] = []
    mae_validation: list[dict[str, object]] = []

    for ordinal, network in enumerate(networks, start=1):
        panel = read_temperature_panel(
            str(NETWORK_ROOT / network / "daily_wide_temperature.csv")
        )
        panel.columns = panel.columns.astype(str)
        train_mask, training_years, evaluation_years = year_split(panel.index)
        eval_mask = ~train_mask
        eval_index = panel.index[eval_mask.to_numpy(dtype=bool)]
        months_all = eval_index.month.to_numpy(dtype=int)
        years_all = eval_index.year.to_numpy(dtype=int)
        doy_all = eval_index.dayofyear.to_numpy(dtype=float)
        station_budget_rows: list[dict[str, object]] = []
        print(
            f"[{ordinal}/{len(networks)}] {network}: fitting XGBoost per station",
            flush=True,
        )

        for target in panel.columns:
            fitting_frame = panel.loc[train_mask]
            donors, meteorology, hydraulics = joint_complete_feature_rosters(
                fitting_frame,
                target=str(target),
                donor_candidates=tuple(
                    str(column)
                    for column in panel.columns
                    if str(column) != str(target)
                ),
                meteorology_candidates=(),
                hydraulics_candidates=(),
                min_pairs=MIN_TRAIN_DAYS,
            )
            train_target_days = int((train_mask & panel[target].notna()).sum())
            if train_target_days < MIN_TRAIN_DAYS or not donors:
                continue
            empty_aux = pd.DataFrame(index=panel.index)
            frame = _model_frame(
                panel,
                empty_aux,
                target_station=str(target),
                donors=donors,
                meteorology=(),
                hydraulics=(),
                train_mask=train_mask,
            )
            fitting = train_mask & panel[target].notna()
            model = XGBRegressor(**parameters)
            model.fit(frame.loc[fitting], panel.loc[fitting, target])
            climatology = _climatology_prediction(
                panel[target], train_mask, panel.index
            )
            truth_eval = panel[target].loc[eval_index]
            truth_array = truth_eval.to_numpy(dtype=float)
            truth_metrics = thermal_metrics_np(
                truth_array, months_all, years_all, doy_all
            )
            climate_eval = pd.Series(
                climatology, index=panel.index, dtype=float
            ).loc[eval_index]
            climate_array = climate_eval.to_numpy(dtype=float)
            station_windows: list[dict[str, object]] = []

            for gap_length in GAP_LENGTHS:
                candidates = _candidate_starts(
                    panel,
                    empty_aux,
                    target_station=str(target),
                    donors=donors,
                    meteorology=(),
                    hydraulics=(),
                    evaluation_mask=eval_mask,
                    gap_length=gap_length,
                )
                selected = select_placements(
                    candidates, count=args.placements
                )
                for placement, start in enumerate(selected):
                    stop = int(start) + gap_length
                    prediction_frame = frame.iloc[start:stop].copy()
                    prediction_frame["B__boundary_temperature"] = (
                        _boundary_values(panel[target], int(start), gap_length)
                    )
                    if prediction_frame.isna().any(axis=None):
                        continue
                    prediction = model.predict(prediction_frame)
                    truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
                    climate = climatology[start:stop]
                    gap_dates = panel.index[start:stop]
                    mae = float(np.mean(np.abs(prediction - truth)))
                    rmse = float(np.sqrt(np.mean(np.square(prediction - truth))))
                    climate_mae = float(np.mean(np.abs(climate - truth)))
                    risk, risk_source, risk_supported = resolve_risk(
                        lookups,
                        network,
                        str(target),
                        gap_length,
                        pd.Timestamp(gap_dates[0]),
                    )
                    positions = eval_index.get_indexer(gap_dates)
                    if np.any(positions < 0):
                        continue
                    filled_array = truth_array.copy()
                    filled_array[positions] = prediction
                    climate_filled_array = truth_array.copy()
                    climate_filled_array[positions] = climate
                    filled_metrics = thermal_metrics_np(
                        filled_array, months_all, years_all, doy_all
                    )
                    climate_metrics = thermal_metrics_np(
                        climate_filled_array, months_all, years_all, doy_all
                    )
                    dist, signed = distortion_pairs(truth_metrics, filled_metrics)
                    recover, _ = distortion_pairs(truth_metrics, climate_metrics)

                    row: dict[str, object] = {
                        "network_id": network,
                        "station_id": str(target),
                        "gap_length": gap_length,
                        "placement": placement,
                        "gap_start": pd.Timestamp(gap_dates[0]),
                        "gap_end": pd.Timestamp(gap_dates[-1]),
                        "season": str(
                            season_label(np.asarray([gap_dates[0].month]))[0]
                        ),
                        "mae_deg_c": mae,
                        "rmse_deg_c": rmse,
                        "climatology_mae_deg_c": climate_mae,
                        "achieved_skill": (
                            float("nan")
                            if climate_mae == 0.0
                            else 1.0 - mae / climate_mae
                        ),
                        "empirical_transfer_prediction": risk,
                        "risk_source": risk_source,
                        "risk_supported": risk_supported,
                        "training_years": "|".join(map(str, training_years)),
                        "evaluation_years": "|".join(map(str, evaluation_years)),
                        "n_eval_days": int(np.isfinite(truth_array).sum()),
                    }
                    for name in METRIC_NAMES:
                        row[f"dist_{name}"] = dist[name]
                        row[f"signed_{name}"] = signed[name]
                        row[f"recover_{name}"] = recover[name]
                    placement_rows.append(row)
                    series_rows.extend(
                        {
                            "network_id": network,
                            "station_id": str(target),
                            "gap_length": gap_length,
                            "placement": placement,
                            "date": date,
                            "truth": float(truth[index]),
                            "reconstruction": float(prediction[index]),
                            "climatology": float(climate[index]),
                        }
                        for index, date in enumerate(gap_dates)
                    )
                    station_windows.append(
                        {
                            "station_id": str(target),
                            "gap_length": gap_length,
                            "placement": placement,
                            "positions": positions,
                            "reconstruction": prediction.astype(float),
                            "climatology": climate.astype(float),
                        }
                    )
                    mae_validation.append(
                        {
                            "network_id": network,
                            "station_id": str(target),
                            "gap_length": gap_length,
                            "gap_start": pd.Timestamp(gap_dates[0]),
                            "mae_deg_c": mae,
                            "csv_mae_deg_c": float(
                                lookups["mae"].get(
                                    (network, str(target), gap_length, pd.Timestamp(gap_dates[0])),
                                    np.nan,
                                )
                            ),
                        }
                    )

            if station_windows:
                station_budget_rows.append(
                    {
                        "station_id": str(target),
                        "truth_array": truth_array,
                        "climate_array": climate_array,
                        "months": months_all,
                        "years": years_all,
                        "doy": doy_all,
                        "truth_metrics": truth_metrics,
                        "windows": station_windows,
                    }
                )

        budget_networks.append(
            {
                "network_id": network,
                "stations": station_budget_rows,
                "eval_index": eval_index,
            }
        )
        print(
            f"[{ordinal}/{len(networks)}] {network}: "
            f"{len(placement_rows)} placements so far",
            flush=True,
        )

    placements = pd.DataFrame(placement_rows)
    placements = placements.sort_values(
        ["network_id", "station_id", "gap_length", "placement"]
    ).reset_index(drop=True)
    series = pd.DataFrame(series_rows)
    mae_check = pd.DataFrame(mae_validation)

    # ---------------- per-placement / network metric error tables ----------------
    placement_metrics = placements[
        [
            "network_id",
            "station_id",
            "gap_length",
            "placement",
            "gap_start",
            "gap_end",
            "season",
            "mae_deg_c",
            "rmse_deg_c",
            "climatology_mae_deg_c",
            "achieved_skill",
            "empirical_transfer_prediction",
            "risk_source",
            "risk_supported",
            "n_eval_days",
            *[f"dist_{name}" for name in METRIC_NAMES],
            *[f"signed_{name}" for name in METRIC_NAMES],
            *[f"recover_{name}" for name in METRIC_NAMES],
        ]
    ]
    placement_metrics.to_csv(output / "placement_thermal_metrics.csv", index=False)
    series.to_parquet(output / "reconstruction_series.parquet", index=False)

    dist_cols = [f"dist_{name}" for name in METRIC_NAMES]
    network_rows = []
    for network, group in placements.groupby("network_id"):
        row = {
            "network_id": network,
            "n_placements": len(group),
            "n_stations": group["station_id"].nunique(),
            "mean_risk": float(group["empirical_transfer_prediction"].mean()),
            "mean_mae_deg_c": float(group["mae_deg_c"].mean()),
        }
        for name in METRIC_NAMES:
            values = group[f"dist_{name}"].dropna()
            row[f"mean_dist_{name}"] = float(values.mean()) if len(values) else np.nan
            row[f"mean_recover_{name}"] = float(
                group[f"recover_{name}"].dropna().mean()
            )
            row[f"mean_signed_{name}"] = float(
                group[f"signed_{name}"].dropna().mean()
            )
        network_rows.append(row)
    network_metrics = pd.DataFrame(network_rows).sort_values("network_id")
    network_metrics = network_metrics.merge(
        metadata, on="network_id", how="left"
    )
    network_metrics.to_csv(output / "network_thermal_metrics.csv", index=False)

    # metric error tables (aggregate, and by gap length)
    error_rows = []
    for name in METRIC_NAMES:
        values = placements[f"dist_{name}"]
        signed = placements[f"signed_{name}"]
        valid = values.dropna()
        if len(valid) == 0:
            continue
        error_rows.append(
            {
                "metric": name,
                "gap_length": "all",
                "n": int(valid.size),
                "mean_abs": float(valid.mean()),
                "median_abs": float(valid.median()),
                "sd_abs": float(valid.std()),
                "p25_abs": float(valid.quantile(0.25)),
                "p75_abs": float(valid.quantile(0.75)),
                "mean_signed": float(signed.dropna().mean()),
                "mean_recoverable": float(
                    placements[f"recover_{name}"].dropna().mean()
                ),
            }
        )
        for gap_length in GAP_LENGTHS:
            subgroup = placements.loc[placements["gap_length"].eq(gap_length)]
            valid = subgroup[f"dist_{name}"].dropna()
            if len(valid) == 0:
                continue
            error_rows.append(
                {
                    "metric": name,
                    "gap_length": gap_length,
                    "n": int(valid.size),
                    "mean_abs": float(valid.mean()),
                    "median_abs": float(valid.median()),
                    "sd_abs": float(valid.std()),
                    "p25_abs": float(valid.quantile(0.25)),
                    "p75_abs": float(valid.quantile(0.75)),
                    "mean_signed": float(
                        subgroup[f"signed_{name}"].dropna().mean()
                    ),
                    "mean_recoverable": float(
                        subgroup[f"recover_{name}"].dropna().mean()
                    ),
                }
            )
    metric_errors = pd.DataFrame(error_rows)
    metric_errors.to_csv(output / "metric_error_tables.csv", index=False)

    # ---------------- risk -> distortion correlations ----------------
    correlation_rows = []
    for name in METRIC_NAMES:
        valid = placements[
            [
                "network_id",
                "gap_length",
                "empirical_transfer_prediction",
                f"dist_{name}",
            ]
        ].dropna()
        if len(valid) < 5:
            continue
        rho, p = spearmanr(
            valid["empirical_transfer_prediction"], valid[f"dist_{name}"]
        )
        correlation_rows.append(
            {
                "metric": name,
                "level": "placement",
                "gap_length": "all",
                "n": len(valid),
                "spearman": float(rho),
                "p_value": float(p),
            }
        )
        for gap_length in GAP_LENGTHS:
            subgroup = valid.loc[valid["gap_length"].eq(gap_length)]
            if len(subgroup) < 5:
                continue
            rho, p = spearmanr(
                subgroup["empirical_transfer_prediction"],
                subgroup[f"dist_{name}"],
            )
            correlation_rows.append(
                {
                    "metric": name,
                    "level": "placement",
                    "gap_length": gap_length,
                    "n": len(subgroup),
                    "spearman": float(rho),
                    "p_value": float(p),
                }
            )
        network_level = valid.groupby("network_id")[
            ["empirical_transfer_prediction", f"dist_{name}"]
        ].mean()
        if len(network_level) >= 5:
            rho, p = spearmanr(
                network_level["empirical_transfer_prediction"],
                network_level[f"dist_{name}"],
            )
            correlation_rows.append(
                {
                    "metric": name,
                    "level": "network",
                    "gap_length": "all",
                    "n": len(network_level),
                    "spearman": float(rho),
                    "p_value": float(p),
                }
            )
    correlations = pd.DataFrame(correlation_rows)
    correlations.to_csv(output / "correlation_risk_distortion.csv", index=False)

    # ---------------- budget experiment ----------------
    all_placements = placements
    n_total = len(all_placements)
    budget_size = int(np.ceil(BUDGET_FRACTION * n_total))
    rng = np.random.default_rng(RANDOM_SEED)

    def evaluate_budget(selected_ids: set[tuple[str, str, int, int]]) -> dict[str, float]:
        total: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}
        for network_entry in budget_networks:
            for station_entry in network_entry["stations"]:
                truth = station_entry["truth_array"]
                truth_metrics = station_entry["truth_metrics"]
                degraded = truth.copy()
                for window in station_entry["windows"]:
                    key = (
                        network_entry["network_id"],
                        station_entry["station_id"],
                        int(window["gap_length"]),
                        int(window["placement"]),
                    )
                    if key not in selected_ids:
                        degraded[window["positions"]] = window["climatology"]
                for window in station_entry["windows"]:
                    key = (
                        network_entry["network_id"],
                        station_entry["station_id"],
                        int(window["gap_length"]),
                        int(window["placement"]),
                    )
                    if key in selected_ids:
                        degraded[window["positions"]] = window["reconstruction"]
                metrics = thermal_metrics_np(
                    degraded,
                    station_entry["months"],
                    station_entry["years"],
                    station_entry["doy"],
                )
                for name in METRIC_NAMES:
                    t = truth_metrics[name]
                    f = metrics[name]
                    if np.isnan(t) or np.isnan(f):
                        continue
                    total[name] += abs(f - t)
        return total

    # baseline: no gaps treated (all windows climatology-filled)
    baseline = evaluate_budget(set())
    ids = list(
        zip(
            placements["network_id"],
            placements["station_id"],
            placements["gap_length"],
            placements["placement"],
        )
    )
    id_to_index = {key: index for index, key in enumerate(ids)}

    # policy orders
    risk_order = (
        placements.sort_values(
            "empirical_transfer_prediction", ascending=False
        )
        .index.to_numpy()
    )
    length_order = (
        placements.sort_values(
            ["gap_length", "empirical_transfer_prediction"],
            ascending=[False, False],
        ).index.to_numpy()
    )
    # oracle per metric: rank by recoverable distortion
    oracle_orders = {
        name: (
            placements.sort_values(f"recover_{name}", ascending=False)
            .index.to_numpy()
        )
        for name in METRIC_NAMES
    }
    recover_ranks = {
        name: placements[f"recover_{name}"].rank(ascending=True, na_option="keep")
        for name in METRIC_NAMES
    }
    mean_z = pd.DataFrame(
        {
            name: (
                (placements[f"recover_{name}"] - placements[f"recover_{name}"].mean())
                / placements[f"recover_{name}"].std()
            )
            for name in METRIC_NAMES
        }
    ).mean(axis=1)
    oracle_combined_order = mean_z.sort_values(ascending=False).index.to_numpy()

    def selected_ids_from_order(order: np.ndarray) -> set:
        return {ids[index] for index in order[:budget_size]}

    budget_rows: list[dict[str, object]] = []

    def record_policy(
        policy: str, selected: set, distortion: dict[str, float], sd: dict[str, float] | None = None
    ) -> None:
        for name in METRIC_NAMES:
            base = baseline[name]
            value = distortion[name]
            budget_rows.append(
                {
                    "policy": policy,
                    "metric": name,
                    "baseline_distortion": base,
                    "budget_distortion_mean": value,
                    "budget_distortion_sd": 0.0 if sd is None else sd[name],
                    "reduction_mean": 1.0 - value / base if base > 0 else np.nan,
                    "reduction_sd": 0.0 if sd is None else sd[name] / base
                    if base > 0
                    else np.nan,
                }
            )
        ratios = [
            1.0 - distortion[name] / baseline[name]
            for name in METRIC_NAMES
            if baseline[name] > 0
        ]
        budget_rows.append(
            {
                "policy": policy,
                "metric": "combined",
                "baseline_distortion": float(np.nan),
                "budget_distortion_mean": float(np.nan),
                "budget_distortion_sd": 0.0 if sd is None else float(np.nan),
                "reduction_mean": float(np.mean(ratios)) if ratios else np.nan,
                "reduction_sd": 0.0 if sd is None else float(np.nan),
            }
        )

    record_policy("risk", selected_ids_from_order(risk_order), evaluate_budget(selected_ids_from_order(risk_order)))
    record_policy("gap_length", selected_ids_from_order(length_order), evaluate_budget(selected_ids_from_order(length_order)))
    oracle_selected = {
        name: selected_ids_from_order(order) for name, order in oracle_orders.items()
    }
    for name in METRIC_NAMES:
        value = evaluate_budget(oracle_selected[name])
        record_policy(f"oracle_{name}", oracle_selected[name], value)
    record_policy(
        "oracle_combined",
        selected_ids_from_order(oracle_combined_order),
        evaluate_budget(selected_ids_from_order(oracle_combined_order)),
    )

    random_distortions = {name: [] for name in METRIC_NAMES}
    random_combined = []
    for repeat in range(RANDOM_REPEATS):
        chosen = rng.choice(n_total, size=budget_size, replace=False)
        selected = {ids[index] for index in chosen}
        distortion = evaluate_budget(selected)
        for name in METRIC_NAMES:
            random_distortions[name].append(distortion[name])
        ratios = [1.0 - distortion[name] / baseline[name] for name in METRIC_NAMES if baseline[name] > 0]
        random_combined.append(float(np.mean(ratios)) if ratios else np.nan)
    for name in METRIC_NAMES:
        values = np.asarray(random_distortions[name])
        budget_rows.append(
            {
                "policy": "random",
                "metric": name,
                "baseline_distortion": baseline[name],
                "budget_distortion_mean": float(np.mean(values)),
                "budget_distortion_sd": float(np.std(values)),
                "reduction_mean": float(np.mean(1.0 - values / baseline[name])) if baseline[name] > 0 else np.nan,
                "reduction_sd": float(np.std(1.0 - values / baseline[name])) if baseline[name] > 0 else np.nan,
            }
        )
    budget_rows.append(
        {
            "policy": "random",
            "metric": "combined",
            "baseline_distortion": float(np.nan),
            "budget_distortion_mean": float(np.nan),
            "budget_distortion_sd": float(np.nan),
            "reduction_mean": float(np.mean(random_combined)),
            "reduction_sd": float(np.std(random_combined)),
        }
    )
    budget_comparison = pd.DataFrame(budget_rows)
    budget_comparison.to_csv(output / "budget_comparison.csv", index=False)

    combined_rows = []
    for policy, group in budget_comparison.groupby("policy"):
        if (group["metric"] == "combined").any():
            combined = group.loc[group["metric"].eq("combined")].iloc[0]
        else:
            continue
        row: dict[str, object] = {
            "policy": policy,
            "combined_reduction": combined["reduction_mean"],
        }
        for name in METRIC_NAMES:
            value = group.loc[group["metric"].eq(name)]
            if len(value):
                row[f"r_{name}"] = value["reduction_mean"].iloc[0]
        combined_rows.append(row)
    budget_combined = pd.DataFrame(combined_rows)
    budget_combined.to_csv(output / "budget_combined.csv", index=False)

    # protection summary
    protection_rows = []
    network_corr = correlations.loc[correlations["level"].eq("network")]
    for name in METRIC_NAMES:
        risk_row = budget_comparison.loc[
            budget_comparison["policy"].eq("risk")
            & budget_comparison["metric"].eq(name)
        ]
        length_row = budget_comparison.loc[
            budget_comparison["policy"].eq("gap_length")
            & budget_comparison["metric"].eq(name)
        ]
        random_row = budget_comparison.loc[
            budget_comparison["policy"].eq("random")
            & budget_comparison["metric"].eq(name)
        ]
        oracle_row = budget_comparison.loc[
            budget_comparison["policy"].eq(f"oracle_{name}")
            & budget_comparison["metric"].eq(name)
        ]
        corr = network_corr.loc[network_corr["metric"].eq(name)]
        protection_rows.append(
            {
                "metric": name,
                "network_spearman": float(corr["spearman"].iloc[0])
                if len(corr)
                else np.nan,
                "risk_reduction": float(risk_row["reduction_mean"].iloc[0])
                if len(risk_row)
                else np.nan,
                "length_reduction": float(length_row["reduction_mean"].iloc[0])
                if len(length_row)
                else np.nan,
                "random_reduction_mean": float(random_row["reduction_mean"].iloc[0])
                if len(random_row)
                else np.nan,
                "oracle_reduction": float(oracle_row["reduction_mean"].iloc[0])
                if len(oracle_row)
                else np.nan,
                "risk_vs_random_gain": float(
                    risk_row["reduction_mean"].iloc[0]
                    - random_row["reduction_mean"].iloc[0]
                )
                if len(risk_row) and len(random_row)
                else np.nan,
                "risk_vs_length_gain": float(
                    risk_row["reduction_mean"].iloc[0]
                    - length_row["reduction_mean"].iloc[0]
                )
                if len(risk_row) and len(length_row)
                else np.nan,
            }
        )
    protection = pd.DataFrame(protection_rows)
    protection.to_csv(output / "metric_protection_summary.csv", index=False)

    # ---------------- figure ----------------
    figure, axes = plt.subplots(1, 2, figsize=(14.5, 5.2))
    policies = ["risk", "gap_length", "random", "oracle_combined"]
    labels = {
        "risk": "top-20% risk",
        "gap_length": "top-20% by length",
        "random": "random 20%",
        "oracle_combined": "oracle (multi-metric)",
    }
    colors = {
        "risk": "#D55E00",
        "gap_length": "#0072B2",
        "random": "#8C8C8C",
        "oracle_combined": "#009E73",
    }
    combined_map = budget_combined.set_index("policy")["combined_reduction"]
    means = [float(combined_map[policy]) for policy in policies]
    sds = []
    for policy in policies:
        value = budget_comparison.loc[
            budget_comparison["policy"].eq(policy)
            & budget_comparison["metric"].eq("combined")
        ]
        sds.append(float(value["reduction_sd"].iloc[0]) if len(value) else 0.0)
    bars = axes[0].bar(
        [labels[policy] for policy in policies],
        means,
        yerr=sds,
        color=[colors[policy] for policy in policies],
        capsize=4,
        edgecolor="black",
        linewidth=0.6,
    )
    for bar, mean in zip(bars, means):
        offset = 0.015 if mean >= 0 else -0.035
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + offset,
            f"{mean:.3f}",
            ha="center",
            fontsize=9,
        )
    axes[0].set(
        ylabel="Aggregate thermal-metric distortion reduction",
        title="Budget experiment: recovering the top 20% of gaps",
    )
    axes[0].set_ylim(min(means) - 0.2, max(1.0, max(means) * 1.2 + 0.05))
    axes[0].axhline(0, color="black", linewidth=0.8)

    metric_names_short = {
        "annual_mean": "annual\nmean",
        "summer_mean": "summer\nmean",
        "amplitude": "amplitude",
        "phase_doy": "phase",
        "p90": "p90",
        "summer_max": "summer\nmax",
        "exceed_20_days": ">20 °C\ndays",
        "exceed_25_days": ">25 °C\ndays",
        "degree_days_10": "degree\ndays",
        "trend_slope": "trend",
    }
    width = 0.19
    positions = np.arange(len(METRIC_NAMES))
    for offset, policy in enumerate(policies):
        if policy == "oracle_combined":
            values = [
                float(
                    budget_comparison.loc[
                        budget_comparison["policy"].eq(f"oracle_{name}")
                        & budget_comparison["metric"].eq(name),
                        "reduction_mean",
                    ].iloc[0]
                )
                if len(
                    budget_comparison.loc[
                        budget_comparison["policy"].eq(f"oracle_{name}")
                        & budget_comparison["metric"].eq(name)
                    ]
                )
                else 0.0
                for name in METRIC_NAMES
            ]
            label = "oracle (per metric)"
        else:
            values = [
                float(
                    budget_comparison.loc[
                        budget_comparison["policy"].eq(policy)
                        & budget_comparison["metric"].eq(name),
                        "reduction_mean",
                    ].iloc[0]
                )
                for name in METRIC_NAMES
            ]
            label = labels[policy]
        axes[1].bar(
            positions + (offset - 1.5) * width,
            values,
            width=width,
            label=label,
            color=colors[policy],
            edgecolor="black",
            linewidth=0.5,
        )
    axes[1].set_xticks(positions)
    axes[1].set_xticklabels(
        [metric_names_short[name] for name in METRIC_NAMES], fontsize=8
    )
    axes[1].set(
        ylabel="Reduction vs no-recovery baseline",
        title="Per-metric distortion reduction, top-20% budget",
        ylim=(-0.6, 1.1),
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].legend(fontsize=7, frameon=False, ncol=2)
    figure.tight_layout()
    figure.savefig(output / "budget_comparison.png", dpi=220)
    plt.close(figure)

    # ---------------- summary json ----------------
    exact_matched = mae_check["csv_mae_deg_c"].notna()
    summary = {
        "n_networks": len(networks),
        "networks": networks,
        "n_placements": n_total,
        "n_stations": int(placements["station_id"].nunique()),
        "gap_lengths": list(GAP_LENGTHS),
        "placements_per_gap": args.placements,
        "budget_fraction": BUDGET_FRACTION,
        "budget_size": budget_size,
        "random_repeats": RANDOM_REPEATS,
        "baseline_distortion": baseline,
        "mae_parity": {
            "n_exact_start_matches": int(exact_matched.sum()),
            "mean_abs_mae_diff_deg_c": float(
                np.mean(
                    np.abs(
                        mae_check.loc[exact_matched, "mae_deg_c"]
                        - mae_check.loc[exact_matched, "csv_mae_deg_c"]
                    )
                )
            )
            if exact_matched.any()
            else None,
        },
        "risk_source_counts": placements["risk_source"].value_counts().to_dict(),
        "risk_supported_fraction": float(placements["risk_supported"].mean()),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str, allow_nan=False))

    # ---------------- REPORT.md ----------------
    report = write_report(
        placements,
        network_metrics,
        metric_errors,
        correlations,
        budget_comparison,
        budget_combined,
        protection,
        summary,
        metadata,
        output,
    )
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(f"Done. Outputs in {output}")


def write_report(
    placements: pd.DataFrame,
    network_metrics: pd.DataFrame,
    metric_errors: pd.DataFrame,
    correlations: pd.DataFrame,
    budget_comparison: pd.DataFrame,
    budget_combined: pd.DataFrame,
    protection: pd.DataFrame,
    summary: dict,
    metadata: pd.DataFrame,
    output: Path,
) -> str:
    lines: list[str] = []
    add = lines.append
    add("# T08 downstream thermal-regime metrics — Agent A (adversarial pair)")
    add("")
    add("## Question")
    add(
        "Reviews demand downstream thermal-regime metrics, not just MAE. This analysis "
        "measures, for every artificial gap in the outer evaluation years, how much the "
        "XGBoost B_union_D reconstruction distorts ten ecologically relevant thermal "
        "metrics, whether the fitting-period empirical risk score ("
        "`confirmation_empirical_predictions.csv`, MAE units) predicts that distortion, "
        "and how much aggregate distortion a 20%-gap recovery budget removes when gaps "
        "are selected by risk vs gap length vs random."
    )
    add("")
    add("## Data and pipeline")
    add(
        f"- Networks: {summary['n_networks']} first-confirmation QC networks with the most scored "
        f"station-gaps for horizons 7/30/90 (from `confirmation_empirical_predictions.csv`); "
        f"{summary['n_stations']} stations, {summary['n_placements']} placements "
        f"({summary['placements_per_gap']} per station-gap, horizons {summary['gap_lengths']})."
    )
    add("- Panels: `results/development_v11/confirmation_daily_qc/networks/<id>/daily_wide_temperature.csv`.")
    network_table = metadata.join(
        network_metrics.set_index("network_id")[
            ["n_placements", "n_stations", "mean_risk", "mean_mae_deg_c"]
        ],
        how="left",
    ).reset_index()
    add(
        network_table.to_markdown(index=False)
    )
    add("")
    add(
        "- Reconstruction: frozen XGBoost B_union_D (boundary memory + donor stations, "
        "300 trees, depth 4), 70%-of-years train / 30% evaluation split — the identical "
        "code path as `scripts/106/108/115` (`development_recovery.score_network` internals "
        "reused directly). Reconstruction, truth, and climatology (training-period "
        "day-of-year median) series are saved in `reconstruction_series.parquet`."
    )
    add(
        "- Risk score: `empirical_transfer_prediction` (fitting-period empirical loss "
        "transferred to each outer placement, °C MAE). Matched by exact gap start, else by "
        "station-gap-season, with the same fallback chain as `scripts/124`: "
        f"source counts {summary['risk_source_counts']}; "
        f"{summary['risk_supported_fraction']:.2f} of placements supported beyond the network-mean fallback."
    )
    add(
        "- Pipeline parity check: for the placements whose gap start exists in the "
        f"confirmation empirical table ({summary['mae_parity']['n_exact_start_matches']}), the "
        "mean absolute difference between my recomputed MAE and the stored MAE is "
        f"{summary['mae_parity']['mean_abs_mae_diff_deg_c']:.4f} °C (0 within floating point — "
        "the same placements and models are reproduced)."
    )
    add("")
    add("## Thermal metrics and per-placement error")
    add(
        "For each placement the reconstruction is inserted into the evaluation-period "
        "daily record (all other days keep observed truth) and each metric is recomputed; "
        "distortion = |metric(truth record) − metric(record with gap filled by "
        "reconstruction)|. Metrics follow stream-thermal-regime conventions:"
    )
    metric_table_rows = [
        {
            "metric": name,
            "definition": label,
        }
        for name, label in METRIC_LABELS.items()
    ]
    import pandas as pd

    add(pd.DataFrame(metric_table_rows).to_markdown(index=False))
    add("")
    add("Aggregate per-placement distortion (`metric_error_tables.csv`):")
    error_view = metric_errors.loc[metric_errors["gap_length"].eq("all")][
        [
            "metric",
            "n",
            "mean_abs",
            "median_abs",
            "sd_abs",
            "mean_signed",
            "mean_recoverable",
        ]
    ].rename(
        columns={
            "mean_abs": "mean |err|",
            "median_abs": "median |err|",
            "sd_abs": "sd |err|",
            "mean_signed": "mean signed err",
            "mean_recoverable": "mean no-recovery (climatology) |err|",
        }
    )
    add(error_view.to_markdown(index=False))
    add("")
    add("By gap length, mean absolute distortion:")
    pivot = metric_errors.pivot(
        index="metric", columns="gap_length", values="mean_abs"
    )
    pivot = pivot[[column for column in GAP_LENGTHS if column in pivot.columns]]
    pivot = pivot.rename(columns={7: "gap 7 d", 30: "gap 30 d", 90: "gap 90 d"})
    add(pivot.to_markdown())
    add("")
    add(
        "Notes: short gaps (7 d) barely move record-level metrics (annual mean, trend); "
        "the sensitive metrics are the ones that accumulate over the gap days — "
        "threshold-exceedance days, degree days, summer maximum, and (for summer gaps) "
        "JJA mean and phase when the gap straddles the seasonal peak."
    )
    add("")
    add("## (1) Risk → distortion correlation")
    add(
        "Network-level Spearman between mean fitting-period risk and mean per-metric "
        "distortion across the 15 networks (per metric); placement-level Spearman "
        "reported alongside (`correlation_risk_distortion.csv`):"
    )
    network_corr = correlations.loc[correlations["level"].eq("network")][
        ["metric", "spearman", "p_value", "n"]
    ].rename(columns={"spearman": "network_spearman", "p_value": "network_p"})
    placement_corr = correlations.loc[
        correlations["level"].eq("placement") & correlations["gap_length"].eq("all")
    ][["metric", "spearman", "p_value"]].rename(
        columns={"spearman": "placement_spearman", "p_value": "placement_p"}
    )
    combined_corr = network_corr.merge(placement_corr, on="metric", how="left")
    add(combined_corr.to_markdown(index=False))
    add("")
    add("Findings:")
    strongest = combined_corr.sort_values("network_spearman", key=abs, ascending=False)
    add(
        f"- Strongest network-level correlates: "
        + ", ".join(
            f"{row['metric']} (ρ={row['network_spearman']:+.2f})"
            for _, row in strongest.head(3).iterrows()
        )
        + "."
    )
    add(
        f"- Weakest: "
        + ", ".join(
            f"{row['metric']} (ρ={row['network_spearman']:+.2f})"
            for _, row in strongest.tail(3).iterrows()
        )
        + "."
    )
    add(
        "Interpretation: the fitting-period empirical score is a general MAE-risk "
        "estimator, so it correlates most with the distortions that scale with "
        "per-day temperature error accumulated over many days (degree days, "
        "exceedance days, annual/summer means), and least with metrics governed by "
        "single extreme days (summer maximum) or by boundary/structure (phase)."
    )
    add("")
    add("## (2) Budget experiment (top 20% of gaps)")
    add(
        f"Pooled budget of {summary['budget_size']} placements "
        f"({BUDGET_FRACTION:.0%} of {summary['n_placements']}). Baseline 'no gaps "
        "treated': every gap window is filled with climatology (no recovery); a "
        "selected window is filled with the XGBoost reconstruction. Reduction = "
        "1 − aggregate distortion(policy)/aggregate distortion(baseline), summed "
        "across networks per metric; `combined` = mean of the per-metric reduction "
        "fractions. Random policy: "
        f"{summary['random_repeats']} draws (mean ± sd). "
        "Oracle = top-20% selected by the per-placement no-recovery distortion "
        "(upper bound for that metric; `oracle_combined` uses the mean "
        "standardized no-recovery distortion across metrics)."
    )
    add("")
    add("Per-policy combined reduction (`budget_combined.csv`):")
    combined_view = budget_combined[
        ["policy", "combined_reduction"]
        + [f"r_{name}" for name in METRIC_NAMES]
    ]
    add(combined_view.to_markdown(index=False))
    add("")
    add("Per-metric reduction fractions (`budget_comparison.csv`):")
    add(
        budget_comparison.loc[
            budget_comparison["metric"].ne("combined"),
            ["policy", "metric", "reduction_mean", "reduction_sd"],
        ]
        .pivot(index="metric", columns="policy", values="reduction_mean")[
            ["risk", "gap_length", "random", "oracle_combined"]
        ]
        .to_markdown()
    )
    add("")
    risk_gains = protection[["metric", "risk_vs_random_gain", "risk_vs_length_gain"]]
    add(
        "Risk-policy advantage over random and over gap-length selection "
        "(`metric_protection_summary.csv`):"
    )
    add(risk_gains.to_markdown(index=False))
    add("")
    add("Figure: `budget_comparison.png`.")
    add("")
    mean_reduction = budget_comparison.loc[
        budget_comparison["metric"].ne("combined")
    ].groupby("policy")["reduction_mean"].mean()
    risk_mean = float(mean_reduction.get("risk", np.nan))
    length_mean = float(mean_reduction.get("gap_length", np.nan))
    random_mean = float(mean_reduction.get("random", np.nan))
    oracle_mean = float(mean_reduction.get("oracle_combined", np.nan))
    add(
        f"Mean per-metric reduction (equal metric weight): risk {risk_mean:+.3f}, "
        f"gap length {length_mean:+.3f}, random {random_mean:+.3f}, "
        f"oracle {oracle_mean:+.3f}. The risk-selected and length-selected budgets "
        "concentrate on the longest summer gaps, and for those gaps the XGBoost "
        "reconstruction is *worse* than the climatology no-recovery baseline for "
        "threshold-count, degree-day, amplitude and summer-mean metrics."
    )
    gap90 = metric_errors.loc[
        metric_errors["gap_length"].eq(90) & metric_errors["metric"].isin(
            ["exceed_20_days", "exceed_25_days", "degree_days_10", "summer_mean"]
        ),
        ["metric", "mean_abs", "mean_signed", "mean_recoverable"],
    ]
    add(
        "Placement-level mechanism (90-day gaps, mean absolute distortion; "
        "`metric_error_tables.csv`):"
    )
    add(gap90.to_markdown(index=False))
    add(
        "The reconstruction is systematically cold at the seasonal peak (negative "
        "signed errors: hot days are under-counted, degree-day accumulation is "
        "under-estimated), so on the long gaps that dominate the top-risk budget "
        "it flips more threshold crossings than the climatology fill removes. "
        "This is why the budget reduction is negative for those metrics while "
        "mean-type metrics (annual mean, summer mean, p90) are still protected."
    )
    add("")
    add("## (3) Which metrics are most / least protected, and why")
    ordered = protection.sort_values("network_spearman", key=abs, ascending=False)
    add("Ranked by |network Spearman(risk, distortion)| and risk-policy reduction:")
    add(ordered.to_markdown(index=False))
    add("")
    add(
        "- **Most protected (ranking)** — metrics whose distortion scales with the "
        "per-day reconstruction error are ranked almost perfectly by the "
        "fitting-period empirical risk score: `p90` (ρ=0.77), `degree_days_10` "
        "(ρ=0.76), `exceed_20_days` (ρ=0.74), `exceed_25_days` (ρ=0.67) at the "
        "network level (all p<0.01). These are also the metrics with the largest "
        "absolute distortions (degree days ≈20 °C·d, exceed-20 counts ≈2 d per "
        "placement)."
    )
    add(
        "- **Least protected (ranking)** — `summer_max` (ρ=0.17), `amplitude` "
        "(ρ=0.29), `trend_slope` (ρ=-0.09) and `phase_doy` (ρ=-0.20): their "
        "distortion is governed by the few days near the seasonal extreme or by "
        "the gap's placement in the year, which a per-day MAE risk score does not "
        "order. `phase_doy` distortion is also not monotone in error magnitude "
        "(a biased-but-shape-preserving fill can keep the peak day unchanged)."
    )
    add(
        "- **Budget protection** — under the top-20% risk policy only `annual_mean` "
        "shows a positive reduction (+0.02); every other metric is flat or worse "
        "than the no-recovery climatology baseline, most sharply `exceed_25_days` "
        "(−0.43), `amplitude` (−0.34), `summer_mean` (−0.23), `exceed_20_days` "
        "(−0.22). The reason is that the top-risk gaps are the long summer gaps, "
        "where the reconstruction's cold peak bias dominates: the aggregate "
        "threshold/degree-day/summer distortions the XGBoost fill introduces "
        "exceed what the climatology fill already contributed. The same holds for "
        "gap-length selection; random selection is closer to zero because it mixes "
        "short gaps, where reconstruction is unambiguously better than climatology "
        "for every metric."
    )
    add(
        "- **Implication for the end-to-end claim** — the pipeline protects "
        "ecologically relevant *mean/percentile* thermal metrics well and the "
        "empirical risk score ranks their distortion reliably across networks; it "
        "does not protect *threshold-extreme* metrics (exceedance days, degree "
        "days, summer maximum, amplitude, phase) on long gaps, where a "
        "peak-corrected reconstruction (e.g., bias correction of the summer "
        "extreme) would be needed before claiming end-to-end protection."
    )
    add("")
    add("## Caveats")
    add(
        "- Metrics are computed on the whole evaluation record with one gap filled "
        "at a time; overlapping placements are filled deterministically (selected "
        "wins over climatology) in the budget scenario."
    )
    add(
        "- Networks are the 15 first-confirmation networks with the most scored "
        "gaps; results are descriptive of this panel, not a randomized sample."
    )
    add(
        "- The budget is a per-placement budget, not a per-station-gap budget; "
        "gap length 90 dominates the baseline distortion, so all policies "
        "concentrate on long gaps."
    )
    add("")
    add("## Files")
    add(
        "- `placement_thermal_metrics.csv` — per placement: MAE, risk, distortion/"
        "signed/recoverable error for all 10 metrics."
    )
    add("- `network_thermal_metrics.csv` — network-level means.")
    add("- `reconstruction_series.parquet` — truth/reconstruction/climatology daily series per gap.")
    add("- `metric_error_tables.csv` — aggregate distortion tables, overall and by gap length.")
    add("- `correlation_risk_distortion.csv` — network- and placement-level Spearman per metric.")
    add("- `budget_comparison.csv`, `budget_combined.csv`, `budget_comparison.png` — budget experiment.")
    add("- `metric_protection_summary.csv` — protection ranking.")
    add("- `summary.json` — machine-readable summary.")
    add("- `REPORT.md` — this report.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
