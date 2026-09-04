#!/usr/bin/env python3
"""Build training-vs-evaluation thermal-drift covariates for the second panel.

PLAN.md 6.1 (non-stationarity stratification): for every scored second-panel
network (57 after attrition: 15 chmi_*, 10 nve_basin_*, 32 usgs2_*), compute
per-station training-vs-evaluation thermal drift covariates and collapse them
to one network-level row so the networks can be stratified into
stable / moderate / drift.

Conventions mirror the route-A thermal state computation exactly
(results/development_v11/route_a_confirmation/thermal_state_changes.csv,
written by scripts/118_stratify_route_a_confirmation.py via
route_a_confirmation.thermal_state_changes):
  * panel reading          : development_recovery.read_temperature_panel
  * year split             : development_recovery.year_split (first 70% of
                             sorted calendar years = training, rest = eval)
  * thermal range          : p95 - p5 of period daily values (NaN dropped)
  * lag-30 autocorrelation : pandas Series.autocorr(30) on period values
                             (identical to route A's _lag_correlation at the
                             integer lag 30 on NaN-free series)
  * thermal_state_shift    : |range_change| >= 0.25 or |acf30_change| >= 0.20

PLAN.md 6.1 additionally wants, per station:
  * annual mean difference  mean(eval) - mean(train) of daily values
  * variance ratio          log2(var_eval / var_train)  (sample variance)
  * donor correlation decay Pearson(station, mean-donor series) inside the
    training vs evaluation years, donors = per-station donor_station_ids
    (placement losses), station itself excluded; the station's own scored
    panel columns are the only donor candidates.

Target stations are the scored stations of each network (unique station_id in
results/development_v11/second_confirmation/scoring/placement_losses.csv).

Outputs (results/v14/p3_drift/):
  network_drift_covariates.csv   one row per network + stratum label
  README.md                      sources, formulas, split, counts, rule
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
    year_split,
)

SCORING_DIR = ROOT / "results/development_v11/second_confirmation/scoring"
PRIMARY_NETWORK_ROOT = ROOT / "results/development_v11/second_confirmation/daily_qc/networks"
FALLBACK_NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
OUTPUT = ROOT / "results/v14/p3_drift"

ROUTE_A_QUALIFIER = 0.25
ROUTE_A_ACF_QUALIFIER = 0.20
MIN_DONOR_PAIRS = 30
VARIANCE_DDOF = 1
TERTILE = {"stable": 1, "moderate": 2, "drift": 3}

NETWORK_COLUMNS = (
    "network_id",
    "domain",
    "n_stations",
    "mean_training_thermal_range",
    "mean_evaluation_thermal_range",
    "mean_range_relative_change",
    "mean_training_acf30",
    "mean_evaluation_acf30",
    "mean_acf30_change",
    "mean_annual_mean_diff",
    "mean_variance_ratio",
    "mean_donor_corr_train",
    "mean_donor_corr_eval",
    "donor_corr_change",
    "n_shift_stations",
    "fraction_shift_stations",
)


def _panel_path(network_id: str) -> Path | None:
    primary = PRIMARY_NETWORK_ROOT / network_id / "daily_wide_temperature.csv"
    if primary.is_file():
        return primary
    fallback = FALLBACK_NETWORK_ROOT / network_id / "daily_wide_temperature.csv"
    if fallback.is_file():
        return fallback
    return None


def _domain(network_id: str) -> str:
    if network_id.startswith("chmi_"):
        return "czechia"
    if network_id.startswith("nve_basin_"):
        return "norway"
    if network_id.startswith("usgs2_"):
        return "united_states"
    raise ValueError(f"unknown provider prefix for {network_id!r}")


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pairwise-finite Pearson correlation requiring >= MIN_DONOR_PAIRS pairs."""
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < MIN_DONOR_PAIRS:
        return float("nan")
    return float(np.corrcoef(x[valid], y[valid])[0, 1])


def _station_thermal_covariates(
    network_id: str,
    station: str,
    daily: pd.DataFrame,
    train_mask: pd.Series,
    donor_ids: tuple[str, ...],
) -> dict | None:
    """Mirror route A thermal_state_changes plus the PLAN 6.1 drift covariates."""
    if station not in daily.columns:
        return None
    training = daily.loc[train_mask, station].dropna().to_numpy(dtype=float)
    evaluation = daily.loc[~train_mask, station].dropna().to_numpy(dtype=float)
    if training.size == 0 or evaluation.size == 0:
        return None
    training_range = float(np.quantile(training, 0.95) - np.quantile(training, 0.05))
    evaluation_range = float(
        np.quantile(evaluation, 0.95) - np.quantile(evaluation, 0.05)
    )
    train_acf30 = (
        float(pd.Series(training).autocorr(30))
        if training.size >= 31 and np.nanstd(training) > 0.0
        else float("nan")
    )
    evaluation_acf30 = (
        float(pd.Series(evaluation).autocorr(30))
        if evaluation.size >= 31 and np.nanstd(evaluation) > 0.0
        else float("nan")
    )
    range_change = float(evaluation_range / training_range - 1.0)
    acf_change = float(evaluation_acf30 - train_acf30)
    thermal_state_shift = bool(
        abs(range_change) >= ROUTE_A_QUALIFIER
        or abs(acf_change) >= ROUTE_A_ACF_QUALIFIER
    )
    annual_mean_diff = float(evaluation.mean() - training.mean())
    var_train = float(np.var(training, ddof=VARIANCE_DDOF))
    var_eval = float(np.var(evaluation, ddof=VARIANCE_DDOF))
    variance_ratio = (
        float(np.log2(var_eval / var_train))
        if var_train > 0.0 and var_eval > 0.0 and training.size >= 2
        else float("nan")
    )
    donor_columns = [
        column
        for column in donor_ids
        if column != station and column in daily.columns
    ]
    donor_corr_train = float("nan")
    donor_corr_eval = float("nan")
    if donor_columns:
        donor = daily[donor_columns].mean(axis=1, skipna=True)
        donor_train = donor.loc[train_mask].to_numpy(dtype=float)
        donor_eval = donor.loc[~train_mask].to_numpy(dtype=float)
        station_train = daily.loc[train_mask, station].to_numpy(dtype=float)
        station_eval = daily.loc[~train_mask, station].to_numpy(dtype=float)
        donor_corr_train = _pearson(station_train, donor_train)
        donor_corr_eval = _pearson(station_eval, donor_eval)
    return {
        "network_id": str(network_id),
        "station_id": str(station),
        "training_thermal_range": training_range,
        "evaluation_thermal_range": evaluation_range,
        "thermal_range_relative_change": range_change,
        "training_acf30": train_acf30,
        "evaluation_acf30": evaluation_acf30,
        "acf30_change": acf_change,
        "annual_mean_diff": annual_mean_diff,
        "variance_ratio": variance_ratio,
        "donor_corr_train": donor_corr_train,
        "donor_corr_eval": donor_corr_eval,
        "thermal_state_shift": thermal_state_shift,
    }


def _network_station_rows(task: tuple) -> list[dict]:
    network_id, panel_path, stations = task
    panel = read_temperature_panel(panel_path)
    daily = panel.copy().sort_index().asfreq("D")
    train_mask, _, _ = year_split(daily.index)
    rows = []
    for station_id, donor_ids in stations:
        row = _station_thermal_covariates(
            network_id, station_id, daily, train_mask, donor_ids
        )
        if row is not None:
            rows.append(row)
    return rows


def _build_tasks(placements: pd.DataFrame) -> list[tuple]:
    tasks = []
    for network_id, group in placements.groupby("network_id"):
        panel_path = _panel_path(str(network_id))
        if panel_path is None:
            raise FileNotFoundError(f"no daily panel for {network_id}")
        stations = []
        for station_id, station_rows in group.groupby("station_id"):
            donors = []
            for value in station_rows["donor_station_ids"].dropna():
                donors.extend(str(value).split("|"))
            stations.append((str(station_id), tuple(dict.fromkeys(donors))))
        tasks.append((str(network_id), str(panel_path), stations))
    return tasks


def _aggregate_network(network_id: str, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    mean = lambda column: float(np.nanmean(frame[column].to_numpy(dtype=float)))
    n_stations = len(frame)
    n_shift = int(frame["thermal_state_shift"].sum())
    return {
        "network_id": str(network_id),
        "domain": _domain(str(network_id)),
        "n_stations": n_stations,
        "mean_training_thermal_range": mean("training_thermal_range"),
        "mean_evaluation_thermal_range": mean("evaluation_thermal_range"),
        "mean_range_relative_change": mean("thermal_range_relative_change"),
        "mean_training_acf30": mean("training_acf30"),
        "mean_evaluation_acf30": mean("evaluation_acf30"),
        "mean_acf30_change": mean("acf30_change"),
        "mean_annual_mean_diff": mean("annual_mean_diff"),
        "mean_variance_ratio": mean("variance_ratio"),
        "mean_donor_corr_train": mean("donor_corr_train"),
        "mean_donor_corr_eval": mean("donor_corr_eval"),
        "donor_corr_change": mean("donor_corr_eval") - mean("donor_corr_train")
        if np.isfinite(mean("donor_corr_train"))
        and np.isfinite(mean("donor_corr_eval"))
        else float("nan"),
        "n_shift_stations": n_shift,
        "fraction_shift_stations": float(n_shift / n_stations),
    }


def _assign_strata(networks: pd.DataFrame) -> pd.DataFrame:
    """Three-way stratum from rank tertiles of a standardized composite.

    Per-network drift signals (all dimensionless magnitudes, PLAN 6.1 triplet):
      s_annual = |mean_annual_mean_diff| / max(mean_training_thermal_range, 1e-6)
      s_variance = |mean_variance_ratio|          (log2 variance ratio scale)
      s_donor   = max(0, mean_donor_corr_train - mean_donor_corr_eval)
                  (donor-correlation decay; NaN when no donor covariate)
    Each signal is standardized across networks as
      z = (s - nanmean(s)) / nanstd(s)   (std < 1e-9 -> z = 0)
    composite = mean of the available z values (>= 1 signal).
    Rank tertiles (ties broken by stable rank ordering) map the lowest third to
    'stable', the middle third to 'moderate', and the highest third to 'drift';
    the 57 networks give 19 / 19 / 19.  Networks without any signal receive
    'unknown'.
    """
    values = networks.copy()
    amplitude = values["mean_training_thermal_range"].to_numpy(dtype=float)
    annual = np.abs(values["mean_annual_mean_diff"].to_numpy(dtype=float))
    s_annual = annual / np.maximum(amplitude, 1e-6)
    s_variance = np.abs(values["mean_variance_ratio"].to_numpy(dtype=float))
    donor_decay = (
        values["mean_donor_corr_train"].to_numpy(dtype=float)
        - values["mean_donor_corr_eval"].to_numpy(dtype=float)
    )
    s_donor = np.maximum(donor_decay, 0.0)
    signals = {"s_annual": s_annual, "s_variance": s_variance, "s_donor": s_donor}
    z_scores = {}
    for name, signal in signals.items():
        finite = np.isfinite(signal)
        if not finite.any():
            z_scores[name] = np.zeros(len(signal))
            continue
        center = float(np.mean(signal[finite]))
        spread = float(np.std(signal[finite]))
        z = np.full(len(signal), np.nan)
        z[finite] = (signal[finite] - center) / spread if spread > 1e-9 else 0.0
        z_scores[name] = z
    z_stack = np.column_stack(
        [z_scores["s_annual"], z_scores["s_variance"], z_scores["s_donor"]]
    )
    composite = np.nanmean(np.where(np.isnan(z_stack), np.nan, z_stack), axis=1)
    stratum = np.full(len(values), "unknown", dtype=object)
    ranked = np.argsort(np.argsort(composite, kind="stable"), kind="stable") + 1
    size = int(len(values))
    for label, lo, hi in (
        ("stable", 1, int(np.ceil(size / 3.0))),
        ("moderate", int(np.ceil(size / 3.0)) + 1, int(np.ceil(2 * size / 3.0))),
        ("drift", int(np.ceil(2 * size / 3.0)) + 1, size),
    ):
        stratum[np.isfinite(composite) & (ranked >= lo) & (ranked <= hi)] = label
    values["stratum"] = stratum
    return values


def main() -> None:
    placements = pd.read_csv(
        SCORING_DIR / "placement_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    networks = sorted(placements["network_id"].unique())
    if not OUTPUT.is_dir():
        OUTPUT.mkdir(parents=True)
    print(f"[p3] {len(networks)} scored second-panel networks", flush=True)
    tasks = _build_tasks(placements)
    started = time.time()
    workers = min(32, max(4, (os.cpu_count() or 1)))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        station_rows = list(pool.map(_network_station_rows, tasks, chunksize=1))
    print(
        f"[p3] per-station covariates done in {time.time() - started:.0f}s "
        f"({workers} workers)",
        flush=True,
    )
    rows = [
        _aggregate_network(task[0], station_rows[index])
        for index, task in enumerate(tasks)
    ]
    networks_frame = pd.DataFrame([row for row in rows if row is not None])
    networks_frame = networks_frame[list(NETWORK_COLUMNS)]
    networks_frame = _assign_strata(networks_frame)
    networks_frame = networks_frame.sort_values("network_id").reset_index(drop=True)
    networks_frame.to_csv(OUTPUT / "network_drift_covariates.csv", index=False)
    summary = {
        "n_networks": int(len(networks_frame)),
        "by_domain": networks_frame.groupby("domain")["network_id"]
        .count()
        .astype(int)
        .to_dict(),
        "by_stratum": networks_frame.groupby("stratum")["network_id"]
        .count()
        .astype(int)
        .to_dict(),
        "domain_by_stratum": networks_frame.groupby(["domain", "stratum"])
        .size()
        .astype(int)
        .to_dict(),
    }
    print(f"[p3] by_domain: {summary['by_domain']}", flush=True)
    print(f"[p3] by_stratum: {summary['by_stratum']}", flush=True)
    print(
        "[p3] domain x stratum: "
        + str(summary["domain_by_stratum"]),
        flush=True,
    )
    print(f"[p3] wrote {OUTPUT / 'network_drift_covariates.csv'}", flush=True)


if __name__ == "__main__":
    main()
