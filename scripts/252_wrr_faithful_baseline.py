#!/usr/bin/env python3
"""F15 - a faithful reimplementation of the Beaufort et al. (2022) air-temperature
climate correction, scored on the same development cases as the in-library air ridge.

Why this exists
---------------
The manuscript pairs the incumbent outage-length rule with "an air regression in
the manner of Beaufort et al. (2022), applied to every record alike" and reports
that pairing as worse than the information-conditioned policy. The object behind
that sentence is `abserr_air_ridge` from the v17 estimator library: a Ridge with
alpha = 1.0 on seven individual air lags (0, 1, 2, 3, 5, 7, 14 d) plus two annual
harmonics, fitted leave-one-year-out over the whole year. That is not the cited
method. This script implements the cited method's climate-correction step and
scores it on the identical cases.

The cited method (Beaufort, A., Diamond, J. S., Sauquet, E., & Moatar, F. (2022),
Spatial extrapolation of stream thermal peaks using heterogeneous time series at a
national scale, Hydrology and Earth System Sciences 26(13), 3477-3495,
https://doi.org/10.5194/hess-26-3477-2022, https://hess.copernicus.org/articles/26/3477/2022/):

  * endpoint: the "thermal peak" Tp = interannual mean of the mean of the 30
    hottest consecutive days of each year, Tw,30 (their Eq. 1);
  * climate correction (their Sect. 2.3): station-specific regressions during
    summer between daily Tw and a *right-aligned moving average of Tair* over
    window lengths ("lags") of 2-10 d; the window whose regression gives the
    highest R2 is selected per station; missing summer Tw is then reconstructed
    from the observed Tair moving average with that regression and Tp recomputed;
  * validation: a permutation test on 30 reference stations with 1-9 introduced
    annual gaps, reporting |Tp,fill - Tp,ref| against |Tp,gap - Tp,ref|; the
    reported figures are absolute biases (median 0.03 C for 1 gap year rising to
    0.25 C for 8, no systematic bias).

Everything the implementation needs - daily mean water temperature and daily mean
air temperature at the station - is present in this study's panel, so no
substitution of a missing input is required. Three documented adaptations are
unavoidable and are listed in method_spec.md: the annual (not interannual) endpoint,
the fitting sample, and the right-alignment reading of the moving average (the last
is carried as an explicit sensitivity).

Outputs (results/wrr_submission_ready/amendments/faithful_baseline/):
  method_spec.md, comparison.csv, contrasts.csv, summary.json, REPORT.md,
  case_errors.parquet, integrity_checks.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_FORCING = ROOT / "data/interim/v18_air_forcing.parquet"
DEFAULT_CASES = ROOT / "results/v17_fitness/step3_cases/cases_air.parquet"
OUT = ROOT / "results/wrr_submission_ready/amendments/faithful_baseline"

# --- the cited method's constants -------------------------------------------
BEAUFORT_LAGS = tuple(range(2, 11))          # 2-10 d moving-average windows
SUMMER_MONTHS = (7, 8)                       # paper: July-August ("summer")
MIN_FIT_DAYS = 120                           # study convention, see method_spec.md
VARIANTS = ("beaufort", "beaufort_trainonly", "beaufort_lagshift", "beaufort_jja")


def _preparse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--forcing", default=None)
    parser.add_argument("--cases", default=None)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--draws", type=int, default=1200)
    parser.add_argument("--verify-networks", type=int, default=2)
    parser.add_argument("--limit-networks", type=int, default=0, help="debug: score only the first N networks")
    args, _ = parser.parse_known_args()
    return args


_PRE = _preparse()
FORCING_PATH = Path(_PRE.forcing) if _PRE.forcing else Path(
    os.environ.get("STREAM_AIR_FORCING", str(DEFAULT_FORCING))
)
CASES_PATH = Path(_PRE.cases) if _PRE.cases else DEFAULT_CASES
os.environ["STREAM_AIR_FORCING"] = str(FORCING_PATH)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool  # noqa: E402
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    hottest_window_mean,
)
from stream_recoverability.experiments.v17_fitness.frontier import frontier_for_score  # noqa: E402
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NETWORK_ROSTER,
    PRIMARY_TOLERANCE_C,
    REALIZATIONS_PER_STATION_YEAR,
    TRUSTED_YEARS,
    stable_seed,
)
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import paired_cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import RETENTION  # noqa: E402

# Filled in the parent before the pool is forked; inherited copy-on-write.
_AIR_STATION: dict[str, pd.Series] = {}
_AIR_NETWORK: dict[str, pd.Series] = {}


# ---------------------------------------------------------------------------
# air forcing (same semantics as panel.air_series_for: station series, else the
# network mean over the station-days present in the forcing table)
# ---------------------------------------------------------------------------
def load_air_series(forcing_path: Path, stations: set[str], networks: set[str]):
    frame = pd.read_parquet(forcing_path, columns=["date", "air_temperature_c", "station_id", "network_id"])
    frame["station_id"] = frame["station_id"].astype(str)
    frame["network_id"] = frame["network_id"].astype(str)

    def to_series(dates, values) -> pd.Series:
        series = pd.Series(pd.to_numeric(values, errors="coerce").to_numpy(dtype=float),
                           index=pd.to_datetime(dates).to_numpy())
        return series[~series.index.duplicated(keep="first")].sort_index()

    by_station: dict[str, pd.Series] = {}
    wanted = frame.loc[frame["station_id"].isin(stations)]
    for key, block in wanted.groupby("station_id", observed=True):
        by_station[str(key)] = to_series(block["date"], block["air_temperature_c"])
    by_network: dict[str, pd.Series] = {}
    wanted_net = frame.loc[frame["network_id"].isin(networks)]
    for key, block in wanted_net.groupby("network_id", observed=True):
        block = block.groupby("date", as_index=False)["air_temperature_c"].mean()
        by_network[str(key)] = to_series(block["date"], block["air_temperature_c"])
    return by_station, by_network


# ---------------------------------------------------------------------------
# the cited regression, fitted from sufficient statistics
# ---------------------------------------------------------------------------
def _fit_from_sums(sums: np.ndarray) -> tuple[np.ndarray, float, int] | None:
    """OLS of y on [1, ma] from [n, Sma, Sma2, Sy, Smay, Sy2].

    Returns (coefficients, R2, n) or None when the sample is too small or the
    design is degenerate. Equivalent to lstsq on the explicit design matrix, and
    checked against it in the integrity block.
    """

    n, s_ma, s_ma2, s_y, s_may, s_y2 = (float(value) for value in sums)
    if n < float(MIN_FIT_DAYS):
        return None
    det = n * s_ma2 - s_ma * s_ma
    if not np.isfinite(det) or det <= 1e-9 * max(1.0, n * s_ma2):
        return None
    coef = np.array([(s_ma2 * s_y - s_ma * s_may) / det, (n * s_may - s_ma * s_y) / det])
    sse = (
        s_y2
        - 2.0 * (coef[0] * s_y + coef[1] * s_may)
        + (coef[0] ** 2 * n + 2.0 * coef[0] * coef[1] * s_ma + coef[1] ** 2 * s_ma2)
    )
    sst = s_y2 - s_y * s_y / n
    r2 = float(1.0 - sse / sst) if sst > 0 else float("nan")
    return coef, r2, int(n)


def _sums_from(values: np.ndarray, y: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """[n, Sma, Sma2, Sy, Smay, Sy2] over the entries selected by ``usable``."""

    ma = values[usable]
    response = y[usable]
    if ma.size == 0:
        return np.zeros(6, dtype=float)
    return np.array(
        [ma.size, ma.sum(), (ma * ma).sum(), response.sum(), (ma * response).sum(), (response * response).sum()],
        dtype=float,
    )


def _select_and_fill(
    lags: tuple[int, ...],
    train_sums: dict[int, np.ndarray],
    ma_year: dict[int, np.ndarray],
    year_usable: dict[int, np.ndarray],
    truth: np.ndarray,
    visible: np.ndarray,
    hidden: np.ndarray,
    *,
    augment: bool,
) -> tuple[np.ndarray, int | None, float, int]:
    """Select the window by R2 and fill the hidden days of the evaluation year."""

    best = None
    for lag in lags:
        sums = train_sums[lag].copy()
        if augment:
            sums += _sums_from(ma_year[lag], truth, year_usable[lag] & visible)
        fitted = _fit_from_sums(sums)
        if fitted is None:
            continue
        coef, r2, n = fitted
        if not np.isfinite(r2):
            continue
        if best is None or r2 > best[1]:
            best = (lag, r2, coef, n)
    fill = np.full(hidden.shape, np.nan, dtype=float)
    if best is None:
        return fill, None, float("nan"), 0
    lag, r2, coef, n = best
    values = ma_year[lag]
    good = hidden & np.isfinite(values)
    fill[good] = coef[0] + coef[1] * values[good]
    return fill, int(lag), float(r2), int(n)


def process_network(job: dict) -> list[dict]:
    network_id = str(job["network_id"])
    source_root = str(job["source_root"])
    daily = load_network_panel(network_id, source_root)
    daily = daily.copy()
    daily.columns = [str(column) for column in daily.columns]
    pool = station_geometry_pool(daily)
    air_network = _AIR_NETWORK.get(network_id)
    rows: list[dict] = []

    for station_id, years in job["stations"].items():
        if station_id not in daily.columns:
            continue
        target = pd.to_numeric(daily[station_id], errors="coerce")
        air_series = _AIR_STATION.get(station_id, air_network)
        if air_series is None:
            continue
        air = air_series.reindex(daily.index)
        index = daily.index
        months = index.month.to_numpy()
        summer = np.isin(months, SUMMER_MONTHS)
        year_values = index.year.to_numpy()
        target_np = target.to_numpy(dtype=float)

        # Right-aligned moving average: the window ends on the day it predicts
        # ("lag L" = the last L days up to and including t). The lagshift variant
        # reads "at lag L" as a window whose right edge is L-1 days earlier.
        ma = {lag: air.rolling(lag).mean().to_numpy(dtype=float) for lag in BEAUFORT_LAGS}
        ma_shift = {lag: air.rolling(lag).mean().shift(lag - 1).to_numpy(dtype=float) for lag in BEAUFORT_LAGS}

        for year, expected_ids in sorted(years.items()):
            year = int(year)
            expected = set(str(value) for value in expected_ids)
            year_mask = year_values == year
            year_index = index[year_mask]
            if len(year_index) < 360:
                continue
            truth = target_np[year_mask]
            if not np.isfinite(truth).all():
                continue
            peak_source = target.loc[target.index.year != year]
            peak_doys = climatological_peak_window(peak_source, exclude_year=None)
            rng = np.random.default_rng(stable_seed(network_id, station_id, year, "leave_one_year_out"))
            realizations = design_for_year(
                year_index, peak_doys, pool, rng=rng,
                n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
            )
            truth_metric = hottest_window_mean(truth)
            train = ~year_mask
            summer_year = summer[year_mask]

            def prepare(ma_source: dict[int, np.ndarray]):
                train_sums, year_usable, ma_year = {}, {}, {}
                finite_target = np.isfinite(target_np)
                for lag in BEAUFORT_LAGS:
                    values = ma_source[lag]
                    train_sums[lag] = _sums_from(
                        values, target_np, summer & train & np.isfinite(values) & finite_target
                    )
                    block_values = values[year_mask]
                    ma_year[lag] = block_values
                    year_usable[lag] = summer_year & np.isfinite(block_values)
                return train_sums, year_usable, ma_year

            train_sums, year_usable, ma_year = prepare(ma)
            train_sums_shift, year_usable_shift, ma_year_shift = prepare(ma_shift)
            # fixed-coefficient variant: the library's information budget (no
            # visible days of the evaluation year in the fit)
            fixed = {}
            for lag in BEAUFORT_LAGS:
                fitted = _fit_from_sums(train_sums[lag])
                if fitted is not None and np.isfinite(fitted[1]):
                    fixed[lag] = fitted

            for realization in realizations:
                if realization.realization_id not in expected:
                    continue
                mask = realization.mask(len(year_index))
                if not mask.any() or mask.all():
                    continue
                visible = ~mask
                hidden = mask
                observed = truth.copy()
                observed[mask] = np.nan

                fill_a, lag_a, r2_a, n_a = _select_and_fill(
                    BEAUFORT_LAGS, train_sums, ma_year, year_usable, truth, visible, hidden, augment=True
                )
                fill_c, lag_c, r2_c, n_c = _select_and_fill(
                    BEAUFORT_LAGS, train_sums_shift, ma_year_shift, year_usable_shift, truth, visible, hidden, augment=True
                )
                # strict season reading of the paper: only the summer holes are
                # reconstructed, everything else stays missing
                fill_j = np.where(hidden & summer_year, fill_a, np.nan)
                fill_b = np.full(hidden.shape, np.nan, dtype=float)
                lag_b, r2_b, n_b = None, float("nan"), 0
                if fixed:
                    lag_b = max(fixed, key=lambda key: fixed[key][1])
                    coef_b, r2_b, n_b = fixed[lag_b]
                    values = ma_year[lag_b]
                    good = hidden & np.isfinite(values)
                    fill_b[good] = coef_b[0] + coef_b[1] * values[good]

                out = {
                    "network_id": network_id,
                    "station_id": station_id,
                    "provider": str(job.get("provider", "")),
                    "year": year,
                    "realization_id": str(realization.realization_id),
                    "mask_total_missing": int(mask.sum()),
                    "mask_longest_run": int(max((length for _, length in realization.runs), default=0)),
                    "mask_n_runs": int(len(realization.runs)),
                    "mask_peak_overlap": peak_overlap_fraction(year_index, mask, peak_doys),
                    "truth_hottest30_recomputed": float(truth_metric),
                    "n_unfilled_beaufort": int(np.isnan(fill_a[hidden]).sum()),
                }
                warm = np.isin(months[year_mask], (5, 6, 7, 8, 9))
                out["mask_warm_observed_fraction"] = float((visible & warm).sum() / max(1, warm.sum()))

                for name, fill in (
                    ("beaufort", fill_a),
                    ("beaufort_trainonly", fill_b),
                    ("beaufort_lagshift", fill_c),
                    ("beaufort_jja", fill_j),
                ):
                    completed = observed.copy()
                    completed[mask] = fill[mask]
                    out[f"hottest30_{name}"] = hottest_window_mean(completed)
                out["lag_beaufort"] = lag_a
                out["r2_beaufort"] = r2_a
                out["n_fit_beaufort"] = n_a
                out["lag_beaufort_lagshift"] = lag_c
                out["r2_beaufort_lagshift"] = r2_c
                out["lag_beaufort_trainonly"] = lag_b
                out["r2_beaufort_trainonly"] = r2_b
                out["n_fit_beaufort_trainonly"] = n_b

                if job.get("verify_air"):
                    models = StationModels(
                        target=target,
                        donors=daily.drop(columns=[station_id]),
                        air=air,
                        train_mask=pd.Series(train, index=index),
                    )
                    lib_fill = models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan)
                    completed = observed.copy()
                    completed[mask] = lib_fill[mask]
                    out["hottest30_air_ridge_repro"] = hottest_window_mean(completed)
                rows.append(out)
    return rows


# ---------------------------------------------------------------------------
# network-clustered paired bootstrap on a difference of means/rates
# ---------------------------------------------------------------------------
def paired_bootstrap(
    frame: pd.DataFrame, left: str, right: str, *, draws: int, seed: int = 0, alpha: float = 0.05
) -> dict:
    block = frame[["network_id", left, right]].copy()
    block[left] = pd.to_numeric(block[left], errors="coerce")
    block[right] = pd.to_numeric(block[right], errors="coerce")
    block = block.dropna(subset=[left, right])
    if block.empty:
        return {"point": float("nan"), "low": float("nan"), "high": float("nan"), "n_pairs": 0, "n_clusters": 0}
    block["_d"] = block[left] - block[right]
    grouped = block.groupby("network_id", sort=True).agg(n=("_d", "size"), d=("_d", "sum"))
    keys = grouped.index.to_numpy()
    counts = grouped["n"].to_numpy(dtype=float)
    deltas = grouped["d"].to_numpy(dtype=float)
    point = float(deltas.sum() / counts.sum())
    rng = np.random.default_rng(int(seed))
    multiplicity = rng.integers(0, len(keys), size=(int(draws), len(keys)))
    weights = np.zeros((int(draws), len(keys)), dtype=float)
    for draw in range(int(draws)):
        weights[draw] = np.bincount(multiplicity[draw], minlength=len(keys))
    denominator = weights @ counts
    values = np.divide(weights @ deltas, denominator, out=np.full(int(draws), np.nan), where=denominator > 0)
    finite = values[np.isfinite(values)]
    return {
        "point": point,
        "low": float(np.quantile(finite, alpha / 2)) if finite.size else float("nan"),
        "high": float(np.quantile(finite, 1 - alpha / 2)) if finite.size else float("nan"),
        "n_pairs": int(len(block)),
        "n_clusters": int(len(keys)),
    }


# ---------------------------------------------------------------------------
def build_station_years(cases: pd.DataFrame) -> dict[str, dict[str, dict[int, tuple[str, ...]]]]:
    """network -> station -> year -> the realization ids the case table stores.

    The year list is taken from the case table itself, so a rebuilt row exists
    only where the study scored one; eligibility (>= MIN_COMPLETE_YEARS complete
    years) is already encoded in that table.
    """

    trusted = pd.read_csv(TRUSTED_YEARS)
    trusted = trusted.loc[trusted["eligible_annual_truth"].astype(bool)]
    trusted["network_id"] = trusted["network_id"].astype(str)
    trusted["station_id"] = trusted["station_id"].astype(str)
    eligible = set(zip(trusted["network_id"], trusted["station_id"]))

    jobs: dict[str, dict[str, dict[int, tuple[str, ...]]]] = {}
    block = cases[["network_id", "station_id", "year", "realization_id"]].drop_duplicates()
    for network_id, station_id, year, realization_id in block.itertuples(index=False):
        key = (str(network_id), str(station_id))
        if key not in eligible:
            continue
        per_station = jobs.setdefault(str(network_id), {}).setdefault(str(station_id), {})
        per_station.setdefault(int(year), []).append(str(realization_id))
    return {
        network: {station: {year: tuple(ids) for year, ids in years.items()} for station, years in stations.items()}
        for network, stations in jobs.items()
    }


def describe(errors: pd.Series, tolerance: float, *, n_supported: int, n_total: int) -> dict:
    values = pd.to_numeric(errors, errors="coerce").dropna().to_numpy(dtype=float)
    if values.size == 0:
        return {"n_cases": 0}
    return {
        "n_cases": int(values.size),
        "n_supported": int(n_supported),
        "support_pct": float(n_supported / n_total * 100) if n_total else float("nan"),
        "mae_c": float(values.mean()),
        "median_ae_c": float(np.median(values)),
        "p90_ae_c": float(np.quantile(values, 0.90)),
        "p95_ae_c": float(np.quantile(values, 0.95)),
        "max_ae_c": float(values.max()),
        "rate_above_0.5": float((values > tolerance).mean()),
        "rate_above_0.5_pct": float((values > tolerance).mean() * 100),
    }


def main() -> int:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(CASES_PATH)
    dev = cases.loc[cases["split_role"] == "development"].reset_index(drop=True)
    dev = attach_policy_errors(dev)
    print(f"development cases: {len(dev)} from {dev['network_id'].nunique()} networks")

    roster = pd.read_csv(NETWORK_ROSTER)
    roster["network_id"] = roster["network_id"].astype(str)
    source_root = roster.set_index("network_id")["source_root"].to_dict()
    provider = roster.set_index("network_id")["provider"].to_dict()

    station_years = build_station_years(dev)
    if int(_PRE.limit_networks):
        keep = sorted(station_years)[: int(_PRE.limit_networks)]
        station_years = {key: station_years[key] for key in keep}
        print(f"DEBUG subset: {len(station_years)} networks only")
    verify_networks = sorted(station_years)[: int(_PRE.verify_networks)]

    stations = {station for block in station_years.values() for station in block}
    networks = set(station_years)
    print(f"rebuilding outages for {len(stations)} stations in {len(networks)} networks; forcing {FORCING_PATH}")
    air_station, air_network = load_air_series(FORCING_PATH, stations, networks)
    _AIR_STATION.update(air_station)
    _AIR_NETWORK.update(air_network)

    jobs = [
        {
            "network_id": network_id,
            "source_root": source_root.get(network_id, "first"),
            "provider": provider.get(network_id, ""),
            "stations": block,
            "verify_air": network_id in verify_networks,
        }
        for network_id, block in sorted(station_years.items())
    ]

    rows: list[dict] = []
    workers = max(1, min(int(_PRE.workers), len(jobs)))
    if workers == 1:
        for job in jobs:
            rows.extend(process_network(job))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for part in pool.map(process_network, jobs, chunksize=1):
                rows.extend(part)
    rebuilt = pd.DataFrame(rows)
    print(f"rebuilt {len(rebuilt)} realization rows")

    # ---- integrity: mask reproduction and library-air-ridge reproduction ----
    checks: dict[str, object] = {
        "forcing_path": str(FORCING_PATH),
        "cases_path": str(CASES_PATH),
        "n_rebuilt_rows": int(len(rebuilt)),
        "n_development_cases": int(len(dev)),
        "min_fit_days": int(MIN_FIT_DAYS),
        "beaufort_lags": list(BEAUFORT_LAGS),
        "debug_limit_networks": int(_PRE.limit_networks),
        "n_stations_rebuilt": int(len(stations)),
        "n_networks_rebuilt": int(len(networks)),
        "workers": int(workers),
        "wall_seconds": None,  # filled at the end
        "summer_months": list(SUMMER_MONTHS),
    }
    checks["mask_checks_source"] = "rebuilt rows joined to the stored case table"
    # air-forcing coverage of the two development panels (the migration-cost fact)
    v17 = pd.read_parquet(
        ROOT / "results/v17_fitness/step3_cases/cases.parquet", columns=["split_role", "air_available"]
    )
    v17_dev = v17.loc[v17["split_role"] == "development"]
    checks["air_available_pct"] = {
        "v17_forcing_panel": float(v17_dev["air_available"].astype(bool).mean() * 100),
        "v18_forcing_panel": float(dev["air_available"].astype(bool).mean() * 100),
        "n_cases_v17_dev": int(len(v17_dev)),
        "n_cases_v18_dev": int(len(dev)),
    }
    checks["forcing_source_note"] = (
        "see results/v18_closure/e5_air_forcing/air_forcing_summary.json for the forcing product description"
    )
    merged = rebuilt.merge(
        dev[
            [
                "network_id", "station_id", "year", "realization_id",
                "total_missing", "longest_run", "peak_overlap", "warm_observed_fraction",
                "truth_hottest30", "abserr_air_ridge", "hottest30_air_ridge",
            ]
        ],
        on=["network_id", "station_id", "year", "realization_id"],
        how="inner",
    )
    checks["n_matched_rows"] = int(len(merged))
    checks["mask_total_missing_mismatches"] = int((merged["mask_total_missing"] != merged["total_missing"]).sum())
    checks["mask_longest_run_mismatches"] = int((merged["mask_longest_run"] != merged["longest_run"]).sum())
    checks["mask_peak_overlap_max_abs_dev"] = float(
        (merged["mask_peak_overlap"] - merged["peak_overlap"]).abs().max()
    )
    checks["mask_warm_fraction_max_abs_dev"] = float(
        (merged["mask_warm_observed_fraction"] - merged["warm_observed_fraction"]).abs().max()
    )
    checks["truth_hottest30_max_abs_dev"] = float(
        (merged["truth_hottest30_recomputed"] - merged["truth_hottest30"]).abs().max()
    )
    verify = merged.loc[merged["hottest30_air_ridge_repro"].notna()]
    checks["library_air_ridge_repro_n"] = int(len(verify))
    checks["library_air_ridge_repro_networks"] = sorted(verify["network_id"].unique().tolist())
    checks["library_air_ridge_repro_max_abs_dev"] = (
        float((verify["hottest30_air_ridge_repro"] - verify["hottest30_air_ridge"]).abs().max()) if len(verify) else float("nan")
    )

    # the sufficient-statistics fit must equal a plain lstsq on the design matrix
    probe = merged.sample(n=min(25, len(merged)), random_state=0)
    lstsq_dev = []
    for row in probe.itertuples(index=False):
        network = str(row.network_id)
        station = str(row.station_id)
        daily = load_network_panel(network, source_root.get(network, "first"))
        daily = daily.copy()
        daily.columns = [str(column) for column in daily.columns]
        target = pd.to_numeric(daily[station], errors="coerce")
        air_series = _AIR_STATION.get(station, _AIR_NETWORK.get(network))
        if air_series is None:
            continue
        air = air_series.reindex(daily.index)
        year_mask = daily.index.year == int(row.year)
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all():
            continue
        summer = np.isin(daily.index.month.to_numpy(), SUMMER_MONTHS)
        summer_year = summer[year_mask]
        rng = np.random.default_rng(stable_seed(network, station, int(row.year), "leave_one_year_out"))
        peak_doys = climatological_peak_window(target.loc[target.index.year != int(row.year)], exclude_year=None)
        pool = station_geometry_pool(daily)
        visible_mask = None
        for realization in design_for_year(
            daily.index[year_mask], peak_doys, pool, rng=rng,
            n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
        ):
            if str(realization.realization_id) == str(row.realization_id):
                visible_mask = ~realization.mask(int(year_mask.sum()))
        if visible_mask is None or not np.isfinite(row.lag_beaufort):
            continue
        lag = int(row.lag_beaufort)
        ma = air.rolling(lag).mean().to_numpy(dtype=float)
        target_np = target.to_numpy(dtype=float)
        train_ok = summer & ~year_mask & np.isfinite(ma) & np.isfinite(target_np)
        year_ok = summer_year & visible_mask & np.isfinite(ma[year_mask])
        design = np.concatenate([ma[train_ok], ma[year_mask][year_ok]])
        response = np.concatenate([target_np[train_ok], truth[year_ok]])
        X = np.column_stack([np.ones(len(response)), design])
        coef, *_ = np.linalg.lstsq(X, response, rcond=None)
        hidden = ~visible_mask
        values = ma[year_mask][hidden]
        good = np.isfinite(values)
        fill = np.full(int(hidden.sum()), np.nan)
        fill[good] = coef[0] + coef[1] * values[good]
        observed = truth.copy()
        observed[hidden] = np.nan
        completed = observed.copy()
        completed[hidden] = fill
        value = hottest_window_mean(completed)
        if np.isfinite(row.hottest30_beaufort) and np.isfinite(value):
            lstsq_dev.append(abs(value - float(row.hottest30_beaufort)))
    checks["sufficient_stats_vs_lstsq_n"] = len(lstsq_dev)
    checks["sufficient_stats_vs_lstsq_max_abs_dev_c"] = float(np.max(lstsq_dev)) if lstsq_dev else float("nan")

    # ---- method errors on the identical cases -------------------------------
    work = dev.merge(
        rebuilt[
            [
                "network_id", "station_id", "year", "realization_id",
                "hottest30_beaufort", "hottest30_beaufort_trainonly", "hottest30_beaufort_lagshift",
                "hottest30_beaufort_jja",
                "lag_beaufort", "r2_beaufort", "n_fit_beaufort", "n_unfilled_beaufort",
            ]
        ],
        on=["network_id", "station_id", "year", "realization_id"],
        how="left",
    )
    print(f"joined: {int(work['hottest30_beaufort'].notna().sum())} of {len(work)} cases carry a faithful reconstruction")
    truth = pd.to_numeric(work["truth_hottest30"], errors="coerce")
    for name in VARIANTS:
        work[f"abserr_{name}"] = (pd.to_numeric(work[f"hottest30_{name}"], errors="coerce") - truth).abs()
    # same fallback convention as the manuscript's table: reconstruction, else climatology
    climatology = pd.to_numeric(work["abserr_doy_climatology"], errors="coerce")
    work["abserr_beaufort_else_clim"] = work["abserr_beaufort"].fillna(climatology)
    work["abserr_beaufort_trainonly_else_clim"] = work["abserr_beaufort_trainonly"].fillna(climatology)
    work["abserr_beaufort_lagshift_else_clim"] = work["abserr_beaufort_lagshift"].fillna(climatology)
    work["abserr_beaufort_jja_else_clim"] = work["abserr_beaufort_jja"].fillna(climatology)
    work["abserr_air_ridge_else_clim"] = pd.to_numeric(work["abserr_air_ridge"], errors="coerce").fillna(climatology)
    work["abserr_donor_ridge_else_clim"] = pd.to_numeric(work["abserr_donor_ridge"], errors="coerce").fillna(climatology)

    rng = np.random.default_rng(5)
    length_score = pd.Series(work["longest_run"].to_numpy(dtype=float) + rng.random(len(work)), index=work.index)
    order = np.argsort(length_score.to_numpy(dtype=float), kind="mergesort")
    n_retained = int(round(float(RETENTION) * len(work)))
    retained = np.zeros(len(work), dtype=bool)
    retained[order[:n_retained]] = True

    methods = {
        # label: (error column actually scored, column whose support is reported)
        "faithful Beaufort (else climatology)": ("abserr_beaufort_else_clim", "abserr_beaufort"),
        "faithful Beaufort, train years only (else climatology)": (
            "abserr_beaufort_trainonly_else_clim", "abserr_beaufort_trainonly"),
        "faithful Beaufort, lagged-window reading (else climatology)": (
            "abserr_beaufort_lagshift_else_clim", "abserr_beaufort_lagshift"),
        "faithful Beaufort, July-August fill only (else climatology)": (
            "abserr_beaufort_jja_else_clim", "abserr_beaufort_jja"),
        "library air ridge alpha=1.0 (else climatology)": ("abserr_air_ridge_else_clim", "abserr_air_ridge"),
        "linear interpolation": ("abserr_linear_interp", "abserr_linear_interp"),
        "donor ridge (else climatology)": ("abserr_donor_ridge_else_clim", "abserr_donor_ridge"),
        "observed days (incumbent estimator)": ("abserr_observed_days", "abserr_observed_days"),
        "information-conditioned policy (reference)": ("abserr_policy", "abserr_policy"),
        "oracle over library methods (not deployable)": ("abserr_oracle_method", "abserr_oracle_method"),
    }
    both_supported = (
        pd.to_numeric(work["abserr_beaufort"], errors="coerce").notna()
        & pd.to_numeric(work["abserr_air_ridge"], errors="coerce").notna()
    )
    subsets = (
        ("all_cases", np.ones(len(work), dtype=bool)),
        ("both_air_methods_supported", both_supported.to_numpy()),
        (f"length_rule_{int(RETENTION * 100)}pct", retained),
    )
    rows_out = []
    for retention_label, subset in subsets:
        block = work.loc[subset]
        for label, (column, support_column) in methods.items():
            if column not in block.columns:
                continue
            support = int(pd.to_numeric(block[support_column], errors="coerce").notna().sum())
            row = {"retention_set": retention_label, "retention": float(subset.mean()), "method": label, "column": column}
            row.update(describe(block[column], PRIMARY_TOLERANCE_C, n_supported=support, n_total=len(block)))
            rows_out.append(row)
    comparison = pd.DataFrame(rows_out)

    # sanity: the length-rule row for the library air ridge must reproduce the
    # manuscript's 15.16% (the number F15 disputes)
    library_row = comparison.loc[
        comparison["method"].eq("library air ridge alpha=1.0 (else climatology)")
        & comparison["retention_set"].eq(f"length_rule_{int(RETENTION * 100)}pct")
    ].iloc[0]
    checks["manuscript_air_ridge_rate_pct_reproduced"] = float(library_row["rate_above_0.5_pct"])

    contrasts_specs = [
        ("faithful Beaufort (else climatology)", "library air ridge alpha=1.0 (else climatology)"),
        ("faithful Beaufort (else climatology)", "linear interpolation"),
        ("faithful Beaufort (else climatology)", "donor ridge (else climatology)"),
        ("faithful Beaufort (else climatology)", "information-conditioned policy (reference)"),
        ("faithful Beaufort, train years only (else climatology)", "library air ridge alpha=1.0 (else climatology)"),
        ("faithful Beaufort, lagged-window reading (else climatology)", "faithful Beaufort (else climatology)"),
        ("faithful Beaufort, train years only (else climatology)", "faithful Beaufort (else climatology)"),
        ("faithful Beaufort, July-August fill only (else climatology)", "faithful Beaufort (else climatology)"),
    ]
    contrast_rows = []
    for retention_label, subset in subsets:
        block = work.loc[subset].reset_index(drop=True)
        for left_label, right_label in contrasts_specs:
            left_col = methods[left_label][0]
            right_col = methods[right_label][0]
            for quantity, transform in (
                ("rate_above_0.5", lambda series: (pd.to_numeric(series, errors="coerce") > PRIMARY_TOLERANCE_C).astype(float)),
                ("mean_abs_error_c", lambda series: pd.to_numeric(series, errors="coerce")),
            ):
                frame = pd.DataFrame(
                    {
                        "network_id": block["network_id"],
                        "left": transform(block[left_col]).to_numpy(dtype=float),
                        "right": transform(block[right_col]).to_numpy(dtype=float),
                    }
                )
                stats = paired_bootstrap(frame, "left", "right", draws=int(_PRE.draws))
                contrast_rows.append(
                    {
                        "retention_set": retention_label,
                        "quantity": quantity,
                        "left": left_label,
                        "right": right_label,
                        "point": stats["point"],
                        "low": stats["low"],
                        "high": stats["high"],
                        "n_pairs": stats["n_pairs"],
                        "n_clusters": stats["n_clusters"],
                    }
                )
    contrasts = pd.DataFrame(contrast_rows)

    # cross-check the vectorised bootstrap against the repository implementation
    block = work.loc[retained].reset_index(drop=True)
    check_frame = pd.DataFrame(
        {
            "network_id": block["network_id"],
            "left": block["abserr_beaufort_else_clim"].to_numpy(dtype=float),
            "right": block["abserr_air_ridge_else_clim"].to_numpy(dtype=float),
        }
    )
    repo_stats = paired_cluster_bootstrap(check_frame, "left", "right", draws=300, seed=0)
    mine = paired_bootstrap(check_frame, "left", "right", draws=300, seed=0)
    checks["bootstrap_point_matches_repo"] = bool(abs(repo_stats["point"] - mine["point"]) < 1e-12)
    checks["bootstrap_repo_point"] = float(repo_stats["point"])
    checks["bootstrap_this_script_point"] = float(mine["point"])
    checks["bootstrap_repo_ci"] = [float(repo_stats["low"]), float(repo_stats["high"])]
    checks["bootstrap_this_script_ci"] = [float(mine["low"]), float(mine["high"])]

    checks["wall_seconds"] = float(time.time() - started)

    # ---- write -------------------------------------------------------------
    comparison.to_csv(OUT / "comparison.csv", index=False)
    contrasts.to_csv(OUT / "contrasts.csv", index=False)
    case_columns = [
        "network_id", "station_id", "provider", "year", "realization_id", "arm", "overlap_class",
        "total_missing", "longest_run", "missing_fraction", "peak_overlap", "warm_observed_fraction",
        "air_available", "truth_hottest30", "abserr_beaufort", "abserr_beaufort_trainonly",
        "abserr_beaufort_lagshift", "abserr_beaufort_jja", "abserr_beaufort_else_clim",
        "abserr_beaufort_jja_else_clim", "abserr_air_ridge_else_clim",
        "abserr_linear_interp", "abserr_donor_ridge_else_clim", "abserr_policy",
        "lag_beaufort", "r2_beaufort", "n_fit_beaufort", "n_unfilled_beaufort",
    ]
    work[[column for column in case_columns if column in work.columns]].to_parquet(OUT / "case_errors.parquet", index=False)

    summary = {
        "finding": "F15 - the manuscript's Beaufort-style baseline is an in-library air ridge, not the cited method",
        "cited_method": {
            "reference": "Beaufort, A., Diamond, J. S., Sauquet, E., & Moatar, F. (2022). Spatial extrapolation of stream thermal peaks using heterogeneous time series at a national scale. Hydrology and Earth System Sciences, 26(13), 3477-3495.",
            "doi": "10.5194/hess-26-3477-2022",
            "url": "https://hess.copernicus.org/articles/26/3477/2022/",
            "climate_correction": "station-specific summer regression of daily Tw on a right-aligned moving average of Tair over 2-10 d windows; window chosen per station by highest R2; hidden days reconstructed from the observed Tair window",
            "endpoint_in_paper": "Tp = interannual mean of the mean of the 30 hottest consecutive days of each year",
            "reported_metric": "absolute bias of Tp after gap filling vs the reference-station Tp, in a 1-9 introduced-gap-year permutation test (median 0.03 C at 1 gap year to 0.25 C at 8; no systematic bias)",
        },
        "implemented": {
            "windows_days": list(BEAUFORT_LAGS),
            "window_selection": "per station-year by highest in-sample R2 of the selected fit sample",
            "season": "July-August (SUMMER_MONTHS)",
            "fallback_convention": "reconstruction where available, else day-of-year climatology (the manuscript's table convention)",
            "variants": {
                "beaufort": "fit on all visible summer days of the record including visible days of the evaluation year",
                "beaufort_trainonly": "fit on summer days outside the evaluation year only (the library estimator's information budget)",
                "beaufort_lagshift": "window right edge L-1 days earlier (the alternative reading of 'at lag L')",
                "beaufort_jja": "only hidden July-August days are reconstructed, as in the paper's summer-only records",
            },
        },
        "integrity": checks,
        "n_cases": int(len(work)),
        "n_networks": int(work["network_id"].nunique()),
        "retention": float(RETENTION),
        "tolerance_c": float(PRIMARY_TOLERANCE_C),
        "bootstrap_draws": int(_PRE.draws),
        "beaufort_lag_choice_counts": {
            str(int(lag)): int(count)
            for lag, count in work["lag_beaufort"].value_counts().sort_index().items()
        },
        "beaufort_support": {
            "n_reconstructed": int(work["hottest30_beaufort"].notna().sum()),
            "pct_reconstructed": float(work["hottest30_beaufort"].notna().mean() * 100),
            "median_r2": float(pd.to_numeric(work["r2_beaufort"], errors="coerce").median()),
            "median_fit_days": float(pd.to_numeric(work["n_fit_beaufort"], errors="coerce").median()),
            "cases_with_unfilled_hidden_days": int((pd.to_numeric(work["n_unfilled_beaufort"], errors="coerce") > 0).sum()),
        },
        "verdict": {},  # filled below
    }

    def at(retention_set: str, method: str) -> dict:
        row = comparison.loc[comparison["retention_set"].eq(retention_set) & comparison["method"].eq(method)].iloc[0]
        return {key: (float(row[key]) if isinstance(row[key], (int, float, np.floating)) else row[key])
                for key in ("n_cases", "n_supported", "support_pct", "mae_c", "median_ae_c", "p90_ae_c",
                            "p95_ae_c", "max_ae_c", "rate_above_0.5_pct")}

    summary["headline"] = {
        label: at(f"length_rule_{int(RETENTION * 100)}pct", label) for label in methods
    }
    summary["headline_all_cases"] = {
        label: at("all_cases", label) for label in methods
    }
    summary["verdict"] = {
        "beaufort_label_defensible": False,
        "reason": (
            "the library estimator named 'Beaufort-style' is a Ridge(alpha=1.0) on seven individual air lags plus "
            "two harmonics fitted over the whole year; the cited method is an OLS regression on a single "
            "right-aligned 2-10 d moving average of air temperature, selected per station by R2, fitted on summer "
            "days only. A faithful reimplementation now exists and is scored here on the identical cases."
        ),
        "recommendation": (
            "either report the faithful reimplementation as the cited-method baseline, or rename the library row to "
            "'in-library air ridge (alpha = 1.0), applied to every record alike' and drop the Beaufort attribution "
            "from that table row."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    (OUT / "integrity_checks.json").write_text(json.dumps(checks, indent=2, default=float), encoding="utf-8")

    print(comparison.to_markdown(index=False, floatfmt=".4f"))
    print()
    print(contrasts.to_markdown(index=False, floatfmt=".5f"))
    print()
    print(json.dumps(checks, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
