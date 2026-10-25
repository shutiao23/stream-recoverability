"""Shared paths, roster and target statistics for the target-recovery study (TR).

The study reuses the opened source archive of the WRR revision for development
and leave-one-region-out validation. It does not read any sealed vault.

Round 2 (configs/wrr_target_recovery_20261022.json, the default) defines years
and seasons per station: Southern Hemisphere records are analysed on a July to
June "hot year", the warm season is the station's five climatologically hottest
consecutive months and degree-days use its four hottest months. The missingness
audit (E1) is shared with round 1. Set TR_CONFIG to select a configuration
explicitly (round 1: configs/wrr_target_recovery_20261021.json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as R3

ROOT = R3.ROOT
CONFIG = Path(os.environ.get("TR_CONFIG", ROOT / "configs" / "wrr_target_recovery_20261022.json"))
if not CONFIG.is_absolute():
    CONFIG = ROOT / CONFIG
_CONFIG = json.loads(CONFIG.read_text())
OUT = ROOT / _CONFIG.get("out", "results/wrr_target_recovery_20261021")
ROUND1 = ROOT / "results" / "wrr_target_recovery_20261021"
# The archive, flow, missingness audit and Australian roster were built once in round 1.
E1 = ROUND1 / "e1_archive"
E1_MISSINGNESS = ROUND1 / "e1_missingness"
AU_ROUND1 = ROUND1 / "e7_sealed"
DOCS = ROOT / "docs" / "reviews" / ("wrr_target_recovery_20261022" if _CONFIG.get("round", 1) == 2 else "wrr_target_recovery_20261021")
SCRATCH = ROOT / "scratch" / "wrr_target_recovery_20261021"
SEASON_MODE = _CONFIG.get("season_mode", "calendar")
AIR_V18 = ROOT / "data" / "interim" / "v18_air_forcing.parquet"
# Same NASA POWER product extended to stations added after v18 (script 429).
AIR = ROOT / "data" / "interim" / "tr_air_forcing.parquet"
if not AIR.exists():
    AIR = AIR_V18
COVERAGE = R3.READY / "major_revision_20261014/p0_06_coverage_recompute/final_coverage_table.csv"
WAVE2_MANIFEST = R3.READY / "p0_07_wave2_ingest/wave2_inputs_manifest.csv"
GROUPS = R3.RUN / "r3_06_independence_risk/complete_network_independence.csv"
ADMISSION = R3.source_cases("leave_one_year_out")
ADMISSION_PRIOR = R3.source_cases("strictly_prior_years")

load_script = R3.load_script

DEGREE_DAYS = "degree_days_peak4" if SEASON_MODE == "hot_year" else "degree_days_jjas"
TARGETS = ("h30", "h7", "annual_mean", "c30", DEGREE_DAYS, "days_above_20", "peak_doy")


def settings() -> dict:
    return json.loads(CONFIG.read_text())


def hemisphere_shift_days(latitude: float | None) -> int:
    """Days added to Southern Hemisphere dates so that calendar years become July-June hot years."""

    if SEASON_MODE != "hot_year" or latitude is None or not np.isfinite(latitude) or latitude >= 0:
        return 0
    return int(_CONFIG["southern_hemisphere_shift_days"])


def hottest_months(daily_climate: np.ndarray, doy: np.ndarray, length: int) -> tuple[int, ...]:
    """The `length` consecutive months (within the hot year) with the warmest mean climatology."""

    month = pd.to_datetime("2021-01-01") + pd.to_timedelta(np.asarray(doy) - 1, unit="D")
    means = pd.Series(np.asarray(daily_climate, dtype=float)).groupby(month.month.to_numpy()).mean().reindex(range(1, 13))
    start = max(range(1, 14 - length), key=lambda m: means.loc[m : m + length - 1].mean())
    return tuple(range(start, start + length))


def station_latitudes() -> dict[str, float]:
    """Latitude by station key from the coordinate files built in round 1."""

    out: dict[str, float] = {}
    coordinates = ROOT / "data/interim/v18_station_coordinates.csv"
    if coordinates.exists():
        frame = pd.read_csv(coordinates, dtype={"station_id": str})
        for row in frame.itertuples(index=False):
            out[f"{row.provider}|{row.station_id}"] = float(row.latitude)
    sites = E1 / "usgs_site_metadata.csv"
    if sites.exists():
        frame = pd.read_csv(sites, dtype={"site_no": str})
        for row in frame.itertuples(index=False):
            out[f"usgs|{row.site_no}"] = float(row.dec_lat_va)
    return out

def target_tolerances() -> dict[str, float]:
    """Per-target tolerances fixed in the preregistration (script 433)."""

    path = OUT / "e2_prereg" / "target_tolerances.json"
    if not path.exists():
        raise RuntimeError("Fix the target tolerances first (scripts/433_tr_prereg.py, round 2: 453_tr2_prereg.py)")
    return {key: float(value) for key, value in json.loads(path.read_text())["tolerance"].items()}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_finite(payload), indent=2, sort_keys=True, allow_nan=False, default=_jsonable) + "\n")


def _finite(value):
    """Missing numbers are written as null rather than as invalid JSON."""

    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Not JSON serialisable: {type(value)}")


def roster() -> pd.DataFrame:
    """Every station of the final analysis panel with its daily input file."""

    coverage = pd.read_csv(COVERAGE, dtype={"station_id": str, "network_id": str})
    manifest = pd.read_csv(WAVE2_MANIFEST, dtype=str).set_index("network_id")
    for network, source in manifest.iterrows():
        match = coverage.network_id.eq(network) & coverage.panel.eq("wave2_confirmation")
        coverage.loc[match, "manifest_input_path"] = source.input_path
    selected = coverage.loc[coverage.in_final_analysis_panel.eq(True)].copy()
    selected["station_key"] = selected.provider.astype(str) + "|" + selected.station_id.astype(str)
    selected = selected.drop_duplicates(["network_id", "station_id"])
    groups = pd.read_csv(GROUPS).set_index("network_id").independence_group
    selected["independence_group"] = selected.network_id.map(groups)
    selected["input_path"] = [str(path if Path(path).is_absolute() else ROOT / path) for path in selected.manifest_input_path]
    return selected


def region_of(provider: str, network_id: str, huc2: str | None = None) -> str:
    """Regions for transfer: each European agency, and USGS by two-digit HUC."""

    if provider != "usgs":
        return provider
    if huc2:
        return f"usgs_huc{huc2}"
    if str(network_id).startswith("huc8_"):
        return f"usgs_huc{str(network_id)[5:7]}"
    return "usgs_unknown"


def window_means(values: np.ndarray, window: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    cumulative = np.concatenate([np.zeros(array.shape[:-1] + (1,)), np.cumsum(array, axis=-1)], axis=-1)
    return (cumulative[..., window:] - cumulative[..., :-window]) / window


def target_statistics(values: np.ndarray, index: pd.DatetimeIndex, threshold_c: float = 20.0, degree_day_months: tuple[int, ...] = (6, 7, 8, 9)) -> dict[str, np.ndarray]:
    """The seven annual targets for one completed year (vector) or many (matrix).

    Degree-days are summed over `degree_day_months` (round 2: the station's four
    climatologically hottest months; round 1: June-September).
    """

    array = np.atleast_2d(np.asarray(values, dtype=float))
    rolled30 = window_means(array, 30)
    month = index.month.to_numpy()
    season = np.isin(month, list(degree_day_months))
    out = {
        "h30": rolled30.max(axis=1),
        "h7": window_means(array, 7).max(axis=1),
        "annual_mean": array.mean(axis=1),
        "c30": rolled30.min(axis=1),
        DEGREE_DAYS: np.clip(array[:, season], 0, None).sum(axis=1),
        "days_above_20": (array > threshold_c).sum(axis=1).astype(float),
        "peak_doy": (np.argmax(rolled30, axis=1) + 15).astype(float),
    }
    if np.ndim(values) == 1:
        return {key: float(value[0]) for key, value in out.items()}
    return out


def mask_from_runs(runs: str, n_days: int) -> np.ndarray:
    mask = np.zeros(int(n_days), dtype=bool)
    for item in str(runs).split(";"):
        if not item:
            continue
        start, length = item.split(":")
        mask[int(start) : int(start) + int(length)] = True
    return mask


def population_weights(cases: pd.DataFrame, population: str) -> pd.Series:
    """Case weights for the four evaluation populations.

    mech: crossed cases, equal weight. deploy: calendar cases reweighted so the
    provider mix matches the real incomplete warm seasons of the archive.
    mnar1/mnar2/mnar_upper: deploy times the exact onset importance weights.
    """

    weights = pd.Series(0.0, index=cases.index)
    if population == "mech":
        weights[cases.design_family.eq("crossed")] = 1.0
        return weights
    calendar = cases.design_family.eq("calendar")
    archive = E1 / "station_years.parquet"
    real = pd.read_parquet(archive, columns=["provider", "edge_year", "fully_active", "complete_year"]) if archive.exists() else pd.DataFrame()
    real = real.loc[~real.edge_year & real.fully_active & ~real.complete_year] if len(real) else real
    target_share = real.provider.value_counts(normalize=True) if len(real) else pd.Series(dtype=float)
    observed_share = cases.loc[calendar, "provider"].value_counts(normalize=True)
    if not set(observed_share.index) & set(target_share.index):
        target_share = observed_share
    ratio = (target_share.reindex(observed_share.index).fillna(0) / observed_share).fillna(0)
    weights[calendar] = cases.loc[calendar, "provider"].map(ratio).astype(float)
    column = {"mnar1": "mnar_logw_k1", "mnar2": "mnar_logw_k2", "mnar_upper": "mnar_logw_upper"}.get(population)
    if column:
        weights[calendar] *= np.exp(cases.loc[calendar, column].fillna(0.0))
    elif population != "deploy":
        raise ValueError(f"Unknown population: {population}")
    return weights


def group_bootstrap(frame: pd.DataFrame, group: str, statistic, draws: int, seed: int) -> np.ndarray:
    """Percentile bootstrap that resamples whole independence groups."""

    rng = np.random.default_rng(seed)
    labels = frame[group].astype(str).to_numpy()
    unique = np.unique(labels)
    positions = {label: np.flatnonzero(labels == label) for label in unique}
    values = []
    for _ in range(int(draws)):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([positions[label] for label in chosen])
        values.append(statistic(frame.iloc[rows]))
    return np.asarray(values, dtype=float)
