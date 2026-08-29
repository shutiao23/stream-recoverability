#!/usr/bin/env python3
"""Missingness-mechanism matrix for the stream-temperature gap-recoverability
project (revision v12, task t06, adversarial pair B).

Reviewers demanded a missingness-mechanism matrix beyond uniform grid gaps.
This script builds, for a bounded subset of 12 first-panel networks (daily QC
temperature panels in results/development_v11/confirmation_daily_qc/), one
mechanism-specific fitting-period empirical stress curve per missingness
mechanism, injects the same mechanism into the evaluation years, recovers the
gaps with the paper's XGBoost recovery family (300 trees, depth 4, lr 0.05,
boundary + donor features, B_union_D), and evaluates risk -> loss transfer
(network-level Spearman and equal-network calibration) per mechanism.

Mechanisms:
  (a) uniform_block      - single contiguous gap, uniform start (paper 2.3 grid)
  (b) multi_block        - gap realised as repeated short blocks + separators
  (c) summer_biased      - gaps start in peak summer (Jul 1 - Aug 31)
  (d) high_temp_biased   - gaps whose window mean temperature is in the warmest
                           25% of the station's fitting-period windows
  (e) discharge_biased   - SKIPPED: no discharge data in data/processed for the
                           confirmation panel (see REPORT.md)
  (f) donor_sync         - target + all donor stations masked in the window
  (g) forcing_outage     - target + air temperature (NASA POWER T2M) masked
  (h) online             - no future boundary feature: model trained and scored
                           with a past-only (left) boundary

Design (mirrors manuscript section 2.3):
  - outer chronological split: first 70% of years = fitting period, remaining
    years = evaluation years;
  - inner split: first 70% of fitting years fit the XGBoost recovery model,
    remaining fitting years receive injected mechanism gaps that form the
    station x horizon x season empirical stress curve;
  - the same mechanism is injected into evaluation years; the outer loss is the
    mean MAE over up to 20 placements per horizon x season cell;
  - predictions fall back direct cell -> station-horizon -> network-horizon ->
    network mean, with the support source recorded.

Every number in the outputs is produced by this script from the QC'd panels.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_data import (  # noqa: E402
    joint_complete_feature_rosters,
)
from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    XGBOOST_PARAMETERS,
    read_temperature_panel,
    select_placements,
    year_split,
)

NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
CANDIDATES_CSV = ROOT / "results/development_v11/confirmation_candidates.csv"
OUTPUT = ROOT / "results/revision_v12/t06_missingness_matrix/agent_b"

NETWORKS = [
    "chmi_labe",
    "chmi_morava",
    "foen_aare_aaregebiet",
    "gkd_bayern_donau",
    "gkd_bayern_isar",
    "lubw_neckar",
    "rws_rijn_lek_nederrijn",
    "huc8_17090004",
    "huc8_10020007",
    "huc8_03150202",
    "huc8_17090012",
    "usgs_missouri_river_huc10",
]

HORIZONS = (7, 30, 90, 180)
SEASONS = ("DJF", "MAM", "JJA", "SON")
SEASON_MONTHS = {
    "DJF": (12, 1, 2),
    "MAM": (3, 4, 5),
    "JJA": (6, 7, 8),
    "SON": (9, 10, 11),
}
PLACEMENTS_PER_CELL = 20
PLACEMENTS_PER_GAP = 20
MIN_TRAIN_DAYS = 365
OUTER_FRACTION = 0.7
INNER_FRACTION = 0.7

# Implemented mechanisms in order.  "model" is the recovery model kind used by
# the mechanism: "bd" = boundary+donors, "bd_ta" = boundary+donors+air
# temperature, "online" = past-only boundary + donors.
MECHANISMS = (
    "uniform_block",
    "multi_block",
    "summer_biased",
    "high_temp_biased",
    "donor_sync",
    "forcing_outage",
    "online",
)
MECHANISM_LABELS = {
    "uniform_block": "(a) uniform single block",
    "multi_block": "(b) multi-block repeated short gaps",
    "summer_biased": "(c) summer-biased (peak-summer starts)",
    "high_temp_biased": "(d) high-temperature-biased",
    "donor_sync": "(f) donor-synchronous outage",
    "forcing_outage": "(g) target + air-temperature outage",
    "online": "(h) online (no future boundary)",
}

SUPPORT_ORDER = ("station_gap_season", "station_gap", "network_gap", "network_mean_fallback")

POWER_URL = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    "?parameters=T2M&community=RE&longitude={lon}&latitude={lat}"
    "&start={start}&end={end}&format=JSON"
)
POWER_UA = "stream-recoverability-confirmatory-builder/1.0"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def season_of(month: int) -> str:
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    raise ValueError(month)


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


def multi_block_layout(gap: int) -> tuple[int, int, int]:
    """Return (n_blocks, block_length, separator_days) for mechanism (b)."""
    n_blocks = min(4, max(2, gap // 3))
    block = int(np.ceil(gap / n_blocks))
    return n_blocks, block, 2


def block_offsets(gap: int) -> np.ndarray:
    """Day offsets (within a gap start) that belong to outage blocks."""
    n_blocks, block, separator = multi_block_layout(gap)
    offsets = []
    for k in range(n_blocks):
        base = k * (block + separator)
        offsets.extend(range(base, base + block))
    return np.asarray(offsets, dtype=int)


def block_span(gap: int) -> int:
    n_blocks, block, separator = multi_block_layout(gap)
    return n_blocks * block + (n_blocks - 1) * separator


# ---------------------------------------------------------------------------
# NASA POWER air temperature (mechanism g)
# ---------------------------------------------------------------------------

def download_power_ta(latitude: float, longitude: float, start: str, end: str,
                      cache_path: Path) -> pd.DataFrame | None:
    """Download daily T2M (deg C) from NASA POWER and cache to a CSV."""
    if cache_path.is_file():
        return pd.read_csv(cache_path, parse_dates=["date"])
    url = POWER_URL.format(lon=longitude, lat=latitude, start=start, end=end)
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": POWER_UA})
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            values = payload["properties"]["parameter"]["T2M"]
            frame = pd.DataFrame(
                [
                    {"date": pd.Timestamp(f"{key[:4]}-{key[4:6]}-{key[6:]}"),
                     "t2m_deg_c": float(value)}
                    for key, value in values.items()
                    if value is not None
                ]
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(cache_path, index=False)
            return frame
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                json.JSONDecodeError, OSError) as error:
            if attempt == 2:
                print(f"  [power] download failed for {cache_path.name}: {error}")
                return None
            time.sleep(3.0 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# model fitting
# ---------------------------------------------------------------------------

def fit_recovery_models(panel: pd.DataFrame, target: str,
                        donors: tuple[str, ...], ta: pd.Series | None,
                        outer_train_mask: pd.Series,
                        fit_mask: pd.Series) -> dict[str, tuple[XGBRegressor, list[str]]]:
    """Fit the B_union_D model, the B_union_D_union_Ta model, and the online
    (past-only boundary) model on ``fit_mask`` years.

    Mirrors the reference pipeline (scripts/106/108): the curve-building model
    is fit on the first 70% of fitting years (nested split), while the outer
    evaluation model is fit on all fitting years (score_network behaviour).
    """
    target_series = panel[target]
    masked_target = target_series.where(outer_train_mask)
    neighbor_boundary = (masked_target.shift(1) + masked_target.shift(-1)) / 2.0
    past_boundary = target_series.shift(1)

    def frame(boundary: pd.Series, use_ta: bool) -> pd.DataFrame:
        features = seasonal_features(panel.index)
        features["B__boundary_temperature"] = boundary
        for donor in donors:
            features[f"D__{donor}"] = panel[donor]
        if use_ta and ta is not None:
            features["M__Ta"] = ta
        return features

    parameters = {**XGBOOST_PARAMETERS, "n_jobs": 1}
    fitting = (fit_mask & target_series.notna()).to_numpy(dtype=bool)

    frames: dict[str, tuple[XGBRegressor, list[str]]] = {}
    for kind, boundary, use_ta in (
        ("bd", neighbor_boundary, False),
        ("bd_ta", neighbor_boundary, True),
        ("online", past_boundary, False),
    ):
        features = frame(boundary, use_ta)
        model = XGBRegressor(**parameters)
        model.fit(features.loc[fitting], target_series.to_numpy(dtype=float)[fitting])
        frames[kind] = (model, list(features.columns))
    return frames


# ---------------------------------------------------------------------------
# candidate windows and placement losses
# ---------------------------------------------------------------------------

def _window_means(values: np.ndarray, gap: int) -> np.ndarray:
    filled = np.nan_to_num(values, nan=0.0)
    cumulative = np.concatenate([[0.0], np.cumsum(filled)])
    return cumulative[gap:] - cumulative[:-gap]


def mechanism_candidates(panel: pd.DataFrame, target: str,
                         donors: tuple[str, ...], ta: pd.Series | None,
                         phase_mask: pd.Series, gap: int,
                         mechanism: str,
                         fit_window_means: np.ndarray | None,
                         q75_by_horizon: dict[int, float] | None,
                         start_months: tuple[int, ...] | None = None,
                         ) -> np.ndarray:
    """Valid gap start indices for a mechanism inside ``phase_mask`` years.

    The phase (year) mask must cover the whole window; the season cell is
    assigned from the START date only (windows may cross season boundaries),
    matching the paper's "candidate starts were divided into DJF, MAM, JJA,
    and SON".
    """
    target_obs = panel[target].notna().to_numpy(dtype=bool)
    phase = np.asarray(phase_mask, dtype=bool)
    size = len(panel)

    if mechanism == "multi_block":
        span = block_span(gap)
        window_obs = (
            np.convolve(target_obs.astype(int), np.ones(span, dtype=int), mode="valid")
            == span
        )
        complete = window_obs & (
            np.convolve(phase.astype(int), np.ones(span, dtype=int), mode="valid")
            == span
        )
        starts = np.arange(len(complete))
        bounded = (starts > 0) & (starts + span < size)
        bounded &= target_obs[np.maximum(starts - 1, 0)]
        bounded &= target_obs[np.minimum(starts + span, size - 1)]
        eligible = starts[complete & bounded]
        if donors:
            donor_obs = (
                np.convolve(
                    panel[list(donors)].notna().all(axis=1).to_numpy(dtype=bool).astype(int),
                    np.ones(span, dtype=int),
                    mode="valid",
                )
                == span
            )
            eligible = eligible[donor_obs[eligible]]
        if start_months is not None:
            months = panel.index.month[eligible].to_numpy(dtype=int)
            eligible = eligible[np.isin(months, np.asarray(start_months))]
        return eligible
    else:
        window = np.ones(gap, dtype=int)
        complete = (
            np.convolve(target_obs.astype(int), window, mode="valid") == gap
        )
        complete &= np.convolve(phase.astype(int), window, mode="valid") == gap
        starts = np.arange(len(complete))
        bounded = (starts > 0) & (starts + gap < size)
        bounded &= target_obs[np.maximum(starts - 1, 0)]
        bounded &= target_obs[np.minimum(starts + gap, size - 1)]
        eligible = starts[complete & bounded]
        if donors:
            donor_obs = (
                np.convolve(
                    panel[list(donors)].notna().all(axis=1).to_numpy(dtype=bool).astype(int),
                    window,
                    mode="valid",
                )
                == gap
            )
            eligible = eligible[donor_obs[eligible]]
        if mechanism == "forcing_outage" and ta is not None:
            ta_obs = np.convolve(ta.notna().to_numpy(dtype=bool).astype(int),
                                 window, mode="valid") == gap
            eligible = eligible[ta_obs[eligible]]
        elif mechanism == "forcing_outage":
            return np.asarray([], dtype=int)
        if mechanism == "summer_biased":
            months = panel.index.month[eligible].to_numpy(dtype=int)
            eligible = eligible[(months == 7) | (months == 8)]
        if start_months is not None:
            months = panel.index.month[eligible].to_numpy(dtype=int)
            eligible = eligible[np.isin(months, np.asarray(start_months))]
        if mechanism == "high_temp_biased" and q75_by_horizon is not None:
            threshold = q75_by_horizon.get(gap)
            if threshold is not None and fit_window_means is not None:
                values = panel[target].to_numpy(dtype=float)
                means = _window_means(values, gap)[eligible]
                eligible = eligible[means >= threshold]
        return eligible


def placement_mae_rows(panel: pd.DataFrame, target: str,
                       donors: tuple[str, ...], ta: pd.Series | None,
                       models: dict[str, tuple[XGBRegressor, list[str]]],
                       starts: np.ndarray, gap: int, mechanism: str,
                       ) -> list[dict]:
    """Score each candidate start under the mechanism and return MAE rows."""
    if not len(starts):
        return []
    model_kind = {
        "uniform_block": "bd",
        "multi_block": "bd",
        "summer_biased": "bd",
        "high_temp_biased": "bd",
        "donor_sync": "bd",
        "forcing_outage": "bd_ta",
        "online": "online",
    }[mechanism]
    model, columns = models[model_kind]
    target_values = panel[target].to_numpy(dtype=float)
    seasonal_full = seasonal_features(panel.index).to_numpy(dtype=float)

    rows: list[np.ndarray] = []
    tags: list[np.ndarray] = []
    truth_parts: list[np.ndarray] = []
    for placement, start in enumerate(starts):
        if mechanism == "multi_block":
            offsets = block_offsets(gap)
            window = start + offsets
        else:
            window = np.arange(start, start + gap, dtype=int)
        left_value = target_values[int(start) - 1]
        if mechanism == "online":
            boundary = np.full(len(window), left_value, dtype=float)
        elif mechanism == "multi_block":
            n_blocks, block, separator = multi_block_layout(gap)
            boundary = np.empty(len(window), dtype=float)
            cursor = 0
            for k in range(n_blocks):
                block_start = start + k * (block + separator)
                block_end = block_start + block
                right_value = target_values[int(block_end)]
                fraction = np.arange(1, block + 1, dtype=float) / (block + 1.0)
                boundary[cursor:cursor + block] = (
                    left_value + fraction * (right_value - left_value)
                )
                left_value = right_value
                cursor += block
        else:
            right_value = target_values[int(start) + gap]
            fraction = np.arange(1, gap + 1, dtype=float) / (gap + 1.0)
            boundary = left_value + fraction * (right_value - left_value)

        block_rows = [seasonal_full[window], boundary[:, None]]
        if donors:
            donor_block = panel.iloc[window][list(donors)].to_numpy(dtype=float)
            if mechanism == "donor_sync":
                donor_block = np.full_like(donor_block, np.nan)
            block_rows.append(donor_block)
        if mechanism == "forcing_outage" and ta is not None:
            ta_block = ta.iloc[window].to_numpy(dtype=float)
            ta_block = np.full(len(window), np.nan)
            block_rows.append(ta_block[:, None])
        rows.append(np.concatenate(block_rows, axis=1))
        tags.append(np.full(len(window), placement, dtype=int))
        truth_parts.append(target_values[window])

    design = np.concatenate(rows, axis=0)
    truth = np.concatenate(truth_parts)
    frame = pd.DataFrame(design, columns=columns)
    prediction = model.predict(frame)
    tag_sorted = np.concatenate(tags)
    maes = []
    for placement in range(len(starts)):
        mask = tag_sorted == placement
        maes.append(
            {
                "placement": int(placement),
                "start_index": int(starts[placement]),
                "mae_deg_c": float(np.mean(np.abs(prediction[mask] - truth[mask]))),
            }
        )
    return maes


# ---------------------------------------------------------------------------
# per-network processing
# ---------------------------------------------------------------------------

def process_network(network: str, power_cache_dir: Path) -> dict:
    """Run all mechanisms for one network; return result tables as dicts."""
    started = time.time()
    result: dict = {
        "network_id": network,
        "units": [],
        "curve_cells": [],
        "eval_cells": [],
        "attrition": [],
        "power": "not_requested",
    }
    panel = read_temperature_panel(
        str(NETWORK_ROOT / network / "daily_wide_temperature.csv")
    )
    panel.columns = panel.columns.astype(str)

    outer_train, fitting_years, evaluation_years = year_split(
        panel.index, training_fraction=OUTER_FRACTION
    )
    inner_cut = min(len(fitting_years) - 1, max(1, round(len(fitting_years) * INNER_FRACTION)))
    model_fit_years = fitting_years[:inner_cut]
    curve_years = fitting_years[inner_cut:]
    model_fit_mask = pd.Series(
        panel.index.year.isin(model_fit_years), index=panel.index, dtype=bool
    )
    curve_mask = pd.Series(
        panel.index.year.isin(curve_years), index=panel.index, dtype=bool
    )
    eval_mask = ~outer_train

    ta: pd.Series | None = None
    coordinates = COORDINATES.get(network)
    if coordinates is not None:
        cache_path = power_cache_dir / f"power_ta_{network}.csv"
        raw = download_power_ta(
            coordinates[0], coordinates[1],
            str(max(panel.index.min().year, 1981)) + "0101",
            panel.index.max().strftime("%Y%m%d"),
            cache_path,
        )
        if raw is not None and len(raw):
            ta = raw.set_index("date")["t2m_deg_c"].reindex(panel.index)
            result["power"] = f"ok_{len(ta.notna())}"
        else:
            result["power"] = "failed"
    else:
        result["power"] = "no_coordinates"

    # Donor selection mirrors scripts/106/108: it uses the outer fitting years
    # (model-fit + curve years), so selected donors have support through the
    # curve period.  Station eligibility follows score_network: at least
    # MIN_TRAIN_DAYS observed target days in the OUTER fitting years.
    fit_frame = panel.loc[outer_train].copy()
    stations: list[str] = []
    station_specs: dict[str, tuple[tuple[str, ...], int]] = {}
    for station in panel.columns:
        try:
            donors, meteorology, hydraulics = joint_complete_feature_rosters(
                fit_frame,
                target=str(station),
                donor_candidates=tuple(
                    str(column) for column in panel.columns if str(column) != str(station)
                ),
                meteorology_candidates=(),
                hydraulics_candidates=(),
                min_pairs=MIN_TRAIN_DAYS,
            )
        except Exception as error:  # pragma: no cover - defensive
            donors = ()
            result["attrition"].append(
                {"network_id": network, "station_id": station,
                 "stage": "donor_selection", "reason": repr(error)}
            )
        outer_days = int((outer_train & panel[station].notna()).sum())
        inner_days = int((model_fit_mask & panel[station].notna()).sum())
        if outer_days < MIN_TRAIN_DAYS or not donors:
            result["attrition"].append(
                {
                    "network_id": network, "station_id": station, "stage": "model_fit",
                    "reason": "insufficient_outer_training_days_or_no_donors"
                    if outer_days < MIN_TRAIN_DAYS else "no_donor_with_minimum_paired_days",
                }
            )
            continue

        # Prune donors that lack evaluation-period paired support; otherwise
        # candidate windows would be impossible in the evaluation years.
        paired_eval = {
            donor: int(((panel[station].notna() & eval_mask) & panel[donor].notna()).sum())
            for donor in donors
        }
        pruned_donors = tuple(
            donor for donor in donors if paired_eval[donor] >= MIN_TRAIN_DAYS
        )
        if len(pruned_donors) != len(donors):
            result["attrition"].append(
                {"network_id": network, "station_id": station,
                 "stage": "donor_pruning",
                 "reason": f"pruned_{len(donors) - len(pruned_donors)}_of_{len(donors)}"}
            )
        if not pruned_donors:
            result["attrition"].append(
                {"network_id": network, "station_id": station,
                 "stage": "model_fit",
                 "reason": "no_donor_with_evaluation_support"}
            )
            continue
        stations.append(str(station))
        station_specs[str(station)] = (pruned_donors, inner_days)

    # Pass 1: build mechanism-specific fitting-period stress curves for every
    # station that has inner model-fit support.
    network_curves: dict[str, dict[tuple[str, int, str], float]] = {
        mechanism: {} for mechanism in MECHANISMS
    }
    for station in stations:
        donors, inner_days = station_specs[station]
        target_values = panel[station].to_numpy(dtype=float)

        # high-temp thresholds from the model-fit period only (no leakage)
        q75_by_horizon: dict[int, float] = {}
        fit_window_means: dict[int, np.ndarray] = {}
        for gap in HORIZONS:
            values = np.nan_to_num(target_values, nan=0.0)
            cumulative = np.concatenate([[0.0], np.cumsum(values)])
            complete = np.convolve(
                panel[station].notna().to_numpy(dtype=bool).astype(int),
                np.ones(gap, dtype=int), mode="valid"
            ) == gap
            complete &= np.convolve(
                model_fit_mask.to_numpy(dtype=bool).astype(int),
                np.ones(gap, dtype=int), mode="valid"
            ) == gap
            means = (cumulative[gap:] - cumulative[:-gap])[complete]
            if len(means):
                fit_window_means[gap] = means
                q75_by_horizon[gap] = float(np.quantile(means, 0.75))

        curve_models = (
            fit_recovery_models(panel, station, donors, ta, outer_train, model_fit_mask)
            if inner_days >= MIN_TRAIN_DAYS
            else None
        )
        for mechanism in MECHANISMS:
            if mechanism == "forcing_outage" and (ta is None or not len(ta.notna())):
                result["attrition"].append(
                    {"network_id": network, "station_id": station,
                     "stage": "forcing_outage", "reason": "no_air_temperature"}
                )
                continue
            if curve_models is None:
                continue
            for gap in HORIZONS:
                for season in SEASONS:
                    candidates = mechanism_candidates(
                        panel, station, donors, ta, curve_mask, gap,
                        mechanism, fit_window_means.get(gap),
                        q75_by_horizon if mechanism == "high_temp_biased" else None,
                        start_months=SEASON_MONTHS[season],
                    )
                    selected = select_placements(candidates, count=PLACEMENTS_PER_CELL)
                    maes = placement_mae_rows(
                        panel, station, donors, ta, curve_models,
                        selected, gap, mechanism,
                    )
                    if not maes:
                        continue
                    cell_mean = float(np.mean([item["mae_deg_c"] for item in maes]))
                    network_curves[mechanism][(station, gap, season)] = cell_mean
                    for item in maes:
                        result["curve_cells"].append(
                            {
                                "network_id": network,
                                "station_id": station,
                                "mechanism": mechanism,
                                "gap_length": int(gap),
                                "season": season,
                                "n_placements": int(len(maes)),
                                "mae_deg_c": item["mae_deg_c"],
                            }
                        )

    # Pass 2: score outer-evaluation placements (recovery model fit on ALL
    # fitting years, score_network behaviour) and predict each placement from
    # the mechanism curve with the reference fallback chain, which uses
    # network-level curve aggregates (stations without their own curve can
    # still receive network_gap / network_mean predictions).
    for station in stations:
        donors, _ = station_specs[station]
        models_eval = fit_recovery_models(
            panel, station, donors, ta, outer_train, outer_train
        )
        target_values = panel[station].to_numpy(dtype=float)
        for mechanism in MECHANISMS:
            if mechanism == "forcing_outage" and (ta is None or not len(ta.notna())):
                continue
            curve = network_curves[mechanism]
            station_cells = {
                (gap, season): value
                for (s, gap, season), value in curve.items()
                if s == station
            }
            station_horizon: dict[int, float] = {}
            for gap in HORIZONS:
                values = [v for (g, _), v in station_cells.items() if g == gap]
                if values:
                    station_horizon[gap] = float(np.mean(values))
            network_horizon: dict[int, float] = {}
            for gap in HORIZONS:
                values = [v for (_, g, _), v in curve.items() if g == gap]
                if values:
                    network_horizon[gap] = float(np.mean(values))
            network_mean = (
                float(np.mean(list(curve.values()))) if curve else float("nan")
            )
            q75_by_horizon: dict[int, float] = {}
            fit_window_means: dict[int, np.ndarray] = {}
            if mechanism == "high_temp_biased":
                values = np.nan_to_num(target_values, nan=0.0)
                cumulative = np.concatenate([[0.0], np.cumsum(values)])
                for gap in HORIZONS:
                    complete = np.convolve(
                        panel[station].notna().to_numpy(dtype=bool).astype(int),
                        np.ones(gap, dtype=int), mode="valid"
                    ) == gap
                    complete &= np.convolve(
                        model_fit_mask.to_numpy(dtype=bool).astype(int),
                        np.ones(gap, dtype=int), mode="valid"
                    ) == gap
                    means = (cumulative[gap:] - cumulative[:-gap])[complete]
                    if len(means):
                        fit_window_means[gap] = means
                        q75_by_horizon[gap] = float(np.quantile(means, 0.75))
            for gap in HORIZONS:
                candidates = mechanism_candidates(
                    panel, station, donors, ta, eval_mask, gap,
                    mechanism, fit_window_means.get(gap),
                    q75_by_horizon if mechanism == "high_temp_biased" else None,
                )
                selected = select_placements(candidates, count=PLACEMENTS_PER_GAP)
                maes = placement_mae_rows(
                    panel, station, donors, ta, models_eval,
                    selected, gap, mechanism,
                )
                for item in maes:
                    start = int(item["start_index"])
                    season = season_of(int(panel.index[start].month))
                    cell_key = (gap, season)
                    if cell_key in station_cells:
                        predicted = station_cells[cell_key]
                        support = "station_gap_season"
                    elif np.isfinite(station_horizon.get(gap, np.nan)):
                        predicted = float(station_horizon[gap])
                        support = "station_gap"
                    elif gap in network_horizon:
                        predicted = float(network_horizon[gap])
                        support = "network_gap"
                    elif np.isfinite(network_mean):
                        predicted = network_mean
                        support = "network_mean_fallback"
                    else:
                        continue
                    result["eval_cells"].append(
                        {
                            "network_id": network,
                            "station_id": station,
                            "mechanism": mechanism,
                            "gap_length": int(gap),
                            "season": season,
                            "n_placements": 1,
                            "observed_mae_deg_c": float(item["mae_deg_c"]),
                            "predicted_mae_deg_c": float(predicted),
                            "support": support,
                        }
                    )

    units = aggregate_units(result["eval_cells"])
    result["units"] = units
    print(f"  [net {network}] {time.time() - started:.1f}s "
          f"stations_ok={len({u['station_id'] for u in units if u['mechanism'] == 'uniform_block'})} "
          f"units={len(units)}", flush=True)
    return result


def aggregate_units(eval_cells: list[dict]) -> list[dict]:
    """Collapse per-placement evaluation rows to station x horizon units."""
    frame = pd.DataFrame(eval_cells)
    if frame.empty:
        return []
    rows = []
    for (network, station, mechanism, gap), group in frame.groupby(
        ["network_id", "station_id", "mechanism", "gap_length"], sort=False
    ):
        weights = group["n_placements"].to_numpy(dtype=float)
        observed = float(np.average(group["observed_mae_deg_c"], weights=weights))
        predicted = float(np.average(group["predicted_mae_deg_c"], weights=weights))
        counts = group["support"].value_counts()
        ranked = sorted(
            ((support, int(counts.get(support, 0))) for support in SUPPORT_ORDER),
            key=lambda item: item[1],
            reverse=True,
        )
        best_count = ranked[0][1]
        candidates = [support for support, count in ranked if count == best_count]
        support_mode = (
            candidates[0]
            if len(candidates) == 1
            else next(
                support for support in reversed(SUPPORT_ORDER)
                if support in candidates
            )
        )
        rows.append(
            {
                "network_id": network,
                "station_id": station,
                "mechanism": mechanism,
                "gap_length": int(gap),
                "n_seasons": int(len(group)),
                "n_placements": int(weights.sum()),
                "observed_recovery_loss": observed,
                "predicted_loss": predicted,
                "support": support_mode,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def point_metrics(units: pd.DataFrame) -> dict:
    """Network Spearman, pooled Spearman, equal-network calibration."""
    observed = units["observed_recovery_loss"].to_numpy(dtype=float)
    predicted = units["predicted_loss"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(units)), predicted])
    counts = units.groupby("network_id")["network_id"].transform("size")
    root_weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    intercept, slope = np.linalg.lstsq(
        design * root_weight[:, None], observed * root_weight, rcond=None
    )[0]
    network = units.groupby("network_id")[
        ["predicted_loss", "observed_recovery_loss"]
    ].mean()
    support_counts = (
        units.groupby("support")["support"].size().reindex(SUPPORT_ORDER).fillna(0)
    )
    return {
        "network_spearman": float(spearmanr(
            network["predicted_loss"], network["observed_recovery_loss"]
        ).statistic),
        "pooled_spearman": float(spearmanr(predicted, observed).statistic),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "n_networks": int(units["network_id"].nunique()),
        "n_station_gaps": int(len(units)),
        "n_placements": int(units["n_placements"].sum()),
        "mean_predicted_loss": float(np.mean(predicted)),
        "mean_observed_loss": float(np.mean(observed)),
        **{f"support_{support}": int(support_counts[support])
           for support in SUPPORT_ORDER},
    }


def cross_predictions(eval_cells: pd.DataFrame, curve_cells: pd.DataFrame,
                      gap_mechanism: str, curve_mechanism: str) -> pd.DataFrame:
    """Predict gap-mechanism evaluation placements with a foreign curve."""
    curve = curve_cells.loc[curve_cells["mechanism"].eq(curve_mechanism)].copy()
    cells = eval_cells.loc[eval_cells["mechanism"].eq(gap_mechanism)].copy()
    rows = []
    for (network, station), station_group in cells.groupby(
        ["network_id", "station_id"], sort=False
    ):
        station_curve = curve.loc[
            curve["network_id"].eq(network) & curve["station_id"].eq(station)
        ]
        cell_map = {
            (int(row.gap_length), row.season): float(
                station_curve.loc[
                    station_curve["gap_length"].eq(row.gap_length)
                    & station_curve["season"].eq(row.season),
                    "mae_deg_c",
                ].mean()
            )
            for row in station_curve[["gap_length", "season"]].drop_duplicates().itertuples()
        }
        station_horizon: dict[int, float] = {}
        for gap in HORIZONS:
            values = [v for (g, _), v in cell_map.items() if g == gap]
            if values:
                station_horizon[gap] = float(np.mean(values))
        network_horizon = {}
        for gap in HORIZONS:
            values = [v for (g, _), v in cell_map.items() if g == gap]
            if values:
                network_horizon[gap] = float(np.mean(values))
        network_mean = (
            float(np.mean(list(cell_map.values()))) if cell_map else float("nan")
        )
        for row in station_group.itertuples():
            key = (int(row.gap_length), row.season)
            if key in cell_map:
                predicted, support = cell_map[key], "station_gap_season"
            elif np.isfinite(station_horizon.get(key[0], np.nan)):
                predicted, support = station_horizon[key[0]], "station_gap"
            elif key[0] in network_horizon:
                predicted, support = network_horizon[key[0]], "network_gap"
            elif np.isfinite(network_mean):
                predicted, support = network_mean, "network_mean_fallback"
            else:
                continue
            rows.append(
                {
                    "network_id": network,
                    "station_id": station,
                    "gap_length": int(row.gap_length),
                    "season": row.season,
                    "n_placements": int(row.n_placements),
                    "observed_recovery_loss": float(row.observed_mae_deg_c),
                    "predicted_loss": float(predicted),
                    "support": support,
                }
            )
    return pd.DataFrame(rows)


def unit_aggregate(cells: pd.DataFrame) -> pd.DataFrame:
    if cells.empty:
        return cells
    rows = []
    for (network, station, gap), group in cells.groupby(
        ["network_id", "station_id", "gap_length"], sort=False
    ):
        weights = group["n_placements"].to_numpy(dtype=float)
        rows.append(
            {
                "network_id": network,
                "station_id": station,
                "gap_length": int(gap),
                "n_placements": int(weights.sum()),
                "observed_recovery_loss": float(
                    np.average(group["observed_recovery_loss"], weights=weights)
                ),
                "predicted_loss": float(
                    np.average(group["predicted_loss"], weights=weights)
                ),
                "support": next(
                    support for support in SUPPORT_ORDER
                    if support in set(group["support"])
                ),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--max-networks", type=int, default=len(NETWORKS))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--skip-power-download", action="store_true")
    args = parser.parse_args()

    global COORDINATES
    candidates = pd.read_csv(CANDIDATES_CSV, dtype={"network_id": str})
    COORDINATES = {
        row.network_id: (float(row.latitude), float(row.longitude))
        for row in candidates.itertuples()
        if pd.notna(row.latitude) and pd.notna(row.longitude)
    }
    for network in NETWORKS[: args.max_networks]:
        if network not in COORDINATES:
            print(f"  [info] {network}: no coordinates in candidates CSV; "
                  f"mechanism (g) will be skipped for it")

    args.output.mkdir(parents=True, exist_ok=True)
    power_cache = args.output / "power_ta_cache"

    networks = NETWORKS[: args.max_networks]
    started = time.time()
    results: list[dict] = []
    if args.workers <= 1 or args.skip_power_download:
        for network in networks:
            results.append(process_network(network, power_cache))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(process_network, network, power_cache)
                       for network in networks]
            for future in futures:
                results.append(future.result())

    units = pd.DataFrame(
        [row for result in results for row in result["units"]]
    )
    curve_cells = pd.DataFrame(
        [row for result in results for row in result["curve_cells"]]
    )
    eval_cells = pd.DataFrame(
        [row for result in results for row in result["eval_cells"]]
    )
    attrition = pd.DataFrame(
        [row for result in results for row in result["attrition"]]
    )

    units.to_csv(args.output / "mechanism_units.csv", index=False)
    curve_cells.to_csv(args.output / "mechanism_curve_cells.csv", index=False)
    eval_cells.to_csv(args.output / "mechanism_eval_cells.csv", index=False)
    attrition.to_csv(args.output / "attrition_log.csv", index=False)

    # per-mechanism metrics: primary table on within-horizon supported units
    # (the paper's 780-unit convention), plus the full-panel numbers including
    # network-mean fallback units
    metric_rows = []
    for mechanism in MECHANISMS:
        subset = units.loc[units["mechanism"].eq(mechanism)].copy()
        supported = subset.loc[
            subset["support"].ne("network_mean_fallback")
        ].copy()
        full_metrics = point_metrics(subset) if len(subset) else {}
        supported_metrics = point_metrics(supported) if len(supported) else {}
        metric_rows.append(
            {
                "mechanism": mechanism,
                **{f"supported_{key}": value
                   for key, value in supported_metrics.items()},
                "full_n_station_gaps": full_metrics.get("n_station_gaps", 0),
                "full_n_networks": full_metrics.get("n_networks", 0),
                "full_network_spearman": full_metrics.get("network_spearman",
                                                           float("nan")),
                "full_pooled_spearman": full_metrics.get("pooled_spearman",
                                                         float("nan")),
                "full_calibration_slope": full_metrics.get("calibration_slope",
                                                           float("nan")),
                "full_mean_predicted_loss": full_metrics.get(
                    "mean_predicted_loss", float("nan")),
                "full_mean_observed_loss": full_metrics.get(
                    "mean_observed_loss", float("nan")),
                "fallback_unit_fraction": float(
                    subset["support"].eq("network_mean_fallback").mean()
                ) if len(subset) else float("nan"),
            }
        )
    metrics = pd.DataFrame(metric_rows)
    metrics["mechanism_label"] = metrics["mechanism"].map(MECHANISM_LABELS)
    metrics.to_csv(args.output / "mechanism_metrics.csv", index=False)

    # missingness x support matrix
    support_matrix = units.groupby(
        ["mechanism", "support"], as_index=False
    ).agg(
        n_station_gaps=("station_id", "size"),
        n_placements=("n_placements", "sum"),
        mean_predicted_loss=("predicted_loss", "mean"),
        mean_observed_loss=("observed_recovery_loss", "mean"),
    )
    support_matrix.to_csv(
        args.output / "missingness_support_matrix.csv", index=False
    )

    # mechanism stress levels: fitting-period curve vs evaluation realization
    stress = []
    for mechanism in MECHANISMS:
        curve = curve_cells.loc[curve_cells["mechanism"].eq(mechanism)]
        outer = units.loc[units["mechanism"].eq(mechanism)]
        stress.append(
            {
                "mechanism": mechanism,
                "curve_mean_mae_deg_c": float(curve["mae_deg_c"].mean())
                if len(curve) else float("nan"),
                "curve_n_cells": int(
                    curve[["network_id", "station_id", "gap_length", "season"]]
                    .drop_duplicates().shape[0]
                ),
                "evaluation_mean_loss_deg_c": float(
                    outer["observed_recovery_loss"].mean()
                ) if len(outer) else float("nan"),
                "evaluation_mean_predicted_deg_c": float(
                    outer["predicted_loss"].mean()
                ) if len(outer) else float("nan"),
            }
        )
    pd.DataFrame(stress).to_csv(
        args.output / "mechanism_stress_levels.csv", index=False
    )

    # mismatch experiment: uniform-block curve applied to summer-biased gaps
    mismatch_directions = [
        ("uniform_block", "summer_biased", "uniform-block curve on summer-biased gaps"),
        ("summer_biased", "uniform_block", "summer-biased curve on uniform-block gaps"),
        ("uniform_block", "donor_sync", "uniform-block curve on donor-synchronous gaps"),
        ("donor_sync", "uniform_block", "donor-synchronous curve on uniform-block gaps"),
        ("uniform_block", "multi_block", "uniform-block curve on multi-block gaps"),
        ("multi_block", "uniform_block", "multi-block curve on uniform-block gaps"),
    ]
    mismatch_rows = []
    for curve_mechanism, gap_mechanism, label in mismatch_directions:
        cross = cross_predictions(eval_cells, curve_cells, gap_mechanism, curve_mechanism)
        matched = eval_cells.loc[eval_cells["mechanism"].eq(gap_mechanism)].copy()
        matched["predicted_loss"] = matched["predicted_mae_deg_c"]
        matched = matched.rename(columns={"observed_mae_deg_c": "observed_recovery_loss"})
        cross = cross.loc[cross["support"].ne("network_mean_fallback")]
        matched = matched.loc[matched["support"].ne("network_mean_fallback")]
        if cross.empty:
            mismatch_rows.append(
                {"direction": label, "curve_mechanism": curve_mechanism,
                 "gap_mechanism": gap_mechanism, "n_station_gaps": 0}
            )
            continue
        cross_units = unit_aggregate(cross)
        matched_units = unit_aggregate(matched)
        cross_metrics = point_metrics(cross_units)
        matched_metrics = point_metrics(matched_units)
        mismatch_rows.append(
            {
                "direction": label,
                "curve_mechanism": curve_mechanism,
                "gap_mechanism": gap_mechanism,
                "n_station_gaps": int(cross_metrics["n_station_gaps"]),
                "n_networks": int(cross_metrics["n_networks"]),
                "matched_network_spearman": matched_metrics["network_spearman"],
                "mismatched_network_spearman": cross_metrics["network_spearman"],
                "spearman_delta": float(
                    cross_metrics["network_spearman"]
                    - matched_metrics["network_spearman"]
                ),
                "matched_calibration_slope": matched_metrics["calibration_slope"],
                "mismatched_calibration_slope": cross_metrics["calibration_slope"],
                "slope_delta": float(
                    cross_metrics["calibration_slope"]
                    - matched_metrics["calibration_slope"]
                ),
                "matched_mean_predicted": matched_metrics["mean_predicted_loss"],
                "mismatched_mean_predicted": cross_metrics["mean_predicted_loss"],
                "mean_observed": cross_metrics["mean_observed_loss"],
                "support_season_cell_fraction": float(
                    cross_units["support"].eq("station_gap_season").mean()
                ),
            }
        )
    pd.DataFrame(mismatch_rows).to_csv(
        args.output / "mismatch_experiment.csv", index=False
    )

    provenance = {
        "task": "t06_missingness_matrix",
        "agent": "b",
        "networks": networks,
        "n_networks": len(networks),
        "mechanisms": list(MECHANISMS),
        "mechanism_e_skipped": (
            "discharge data not available in data/processed for the "
            "confirmation panel"
        ),
        "horizons": list(HORIZONS),
        "seasons": list(SEASONS),
        "placements_per_cell": PLACEMENTS_PER_CELL,
        "min_train_days": MIN_TRAIN_DAYS,
        "xgboost": {
            "n_estimators": XGBOOST_PARAMETERS["n_estimators"],
            "max_depth": XGBOOST_PARAMETERS["max_depth"],
            "learning_rate": XGBOOST_PARAMETERS["learning_rate"],
        },
        "outer_fraction": OUTER_FRACTION,
        "inner_fraction": INNER_FRACTION,
        "runtime_seconds": round(time.time() - started, 1),
        "power_status": {result["network_id"]: result["power"]
                         for result in results},
    }
    (args.output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("\n=== mechanism metrics (within-horizon supported units) ===")
    print(metrics[["mechanism_label", "supported_network_spearman",
                   "supported_pooled_spearman", "supported_calibration_slope",
                   "supported_n_station_gaps", "supported_n_networks",
                   "supported_mean_predicted_loss",
                   "supported_mean_observed_loss",
                   "fallback_unit_fraction"]].to_string(index=False))
    print("\n=== mismatch experiment ===")
    mismatch = pd.DataFrame(mismatch_rows)
    print(mismatch.to_string(index=False))
    print(f"\nElapsed {time.time() - started:.1f}s. Outputs in {args.output}")


if __name__ == "__main__":
    main()
