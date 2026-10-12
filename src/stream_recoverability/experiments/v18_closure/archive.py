"""The archive as it actually is, holes included.

v17 defines its evaluation population as fully observed calendar years, which
is the only way to have truth. The consequence is that the 2,422 station-years
that really do have holes in them appear in that programme only as a source of
outage geometry. This module rebuilds them as first-class objects, because they
are the population every screening rule is ultimately for.

Everything here is computed from information an analyst holds at decision time:
the observed days of the year in question and the station's own other years.
Nothing reads a hidden day, because for these records there is nothing to read.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.panel import load_network_panel, station_roster
from stream_recoverability.experiments.v18_closure.paths import (
    MIN_DAYS_IN_YEAR,
    PEAK_WINDOW_DAYS,
    WARM_MONTHS,
)

MIN_OBSERVATIONS = 400
MIN_COMPLETE_YEARS_FOR_CLIMATOLOGY = 2
FLANK_DAYS = 7


@dataclass(frozen=True)
class StationJob:
    network_id: str
    station_id: str
    provider: str
    source_root: str


def station_jobs() -> list[StationJob]:
    """Every eligible station in the v17 panel, as a picklable job list."""

    roster = station_roster()
    roster = roster.loc[roster["eligible_station"]]
    return [
        StationJob(
            network_id=str(row.network_id),
            station_id=str(row.station_id),
            provider=str(row.provider),
            source_root=str(row.source_root),
        )
        for row in roster.itertuples()
    ]


def _trimmed_series(job: StationJob) -> pd.Series | None:
    """The station's daily series, trimmed to its own observed span.

    Leading and trailing NaN are absence of a deployed logger, not an outage,
    and counting them as missing data would invent gaps that nobody ever had.
    """

    try:
        panel = load_network_panel(job.network_id, job.source_root)
    except (FileNotFoundError, ValueError, KeyError):
        return None
    columns = {str(c): c for c in panel.columns}
    if job.station_id not in columns:
        return None
    series = pd.to_numeric(panel[columns[job.station_id]], errors="coerce")
    if series.notna().sum() < MIN_OBSERVATIONS:
        return None
    return series.loc[series.first_valid_index() : series.last_valid_index()]


def climatological_peak_doys(series: pd.Series, complete_years: np.ndarray) -> np.ndarray | None:
    """Day-of-year indices of the station's climatological hottest window.

    Built from the station's fully observed years only, so it is the same
    quantity the v17 screen conditions on and is available to an analyst facing
    an incomplete year.
    """

    if len(complete_years) < MIN_COMPLETE_YEARS_FOR_CLIMATOLOGY:
        return None
    block = series.loc[series.index.year.isin(complete_years)]
    climatology = (
        block.groupby(block.index.dayofyear).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    )
    values = climatology.to_numpy()
    padded = np.concatenate([values, values[: PEAK_WINDOW_DAYS - 1]])
    rolling = np.convolve(padded, np.ones(PEAK_WINDOW_DAYS) / PEAK_WINDOW_DAYS, mode="valid")[:366]
    start = int(np.nanargmax(rolling)) + 1
    return np.array([((start - 1 + offset) % 366) + 1 for offset in range(PEAK_WINDOW_DAYS)], dtype=int)


def _runs(missing: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    edges = np.diff(np.concatenate([[0], missing.view(np.int8), [0]]))
    return np.where(edges == 1)[0], np.where(edges == -1)[0]


def station_year_rows(job: StationJob) -> list[dict]:
    """One row per calendar year the station covers, complete or not."""

    series = _trimmed_series(job)
    if series is None:
        return []
    frame = pd.DataFrame({"value": series.to_numpy()}, index=series.index)
    frame["year"] = frame.index.year
    frame["doy"] = frame.index.dayofyear
    frame["month"] = frame.index.month

    complete = frame.groupby("year")["value"].apply(
        lambda block: bool(block.notna().all()) and len(block) >= 365
    )
    complete_years = np.asarray(complete[complete].index)
    peak_doys = climatological_peak_doys(series, complete_years)
    if peak_doys is None:
        return []

    rows: list[dict] = []
    for year, block in frame.groupby("year"):
        if len(block) < MIN_DAYS_IN_YEAR:
            continue
        missing = block["value"].isna().to_numpy()
        starts, ends = _runs(missing)
        in_peak = np.isin(block["doy"].to_numpy(), peak_doys)
        warm = np.isin(block["month"].to_numpy(), WARM_MONTHS)
        rows.append(
            {
                "network_id": job.network_id,
                "station_id": job.station_id,
                "provider": job.provider,
                "year": int(year),
                "n_days": int(len(block)),
                "complete": bool(missing.sum() == 0),
                "n_missing": int(missing.sum()),
                "missing_fraction": float(missing.mean()),
                "longest_run": int((ends - starts).max()) if len(starts) else 0,
                "n_runs": int(len(starts)),
                "peak_missing_fraction": float(missing[in_peak].mean()) if in_peak.any() else float("nan"),
                "warm_observed_fraction": float((~missing & warm).sum() / max(1, warm.sum())),
                "peak_window_start_doy": int(peak_doys[0]),
            }
        )
    return rows


def gap_rows(job: StationJob) -> list[dict]:
    """One row per real interior gap, with the anomaly on each flank.

    The flank anomalies are the test of whether missingness is informative: if
    a logger is lost to a flood or buried by ice, the days either side of the
    gap should not look like an ordinary day of that date.
    """

    series = _trimmed_series(job)
    if series is None:
        return []
    doy = series.index.dayofyear
    climatology = series.groupby(doy).mean()
    anomaly = series - pd.Series(climatology.reindex(doy).to_numpy(), index=series.index)
    missing = series.isna().to_numpy()
    starts, ends = _runs(missing)
    rows: list[dict] = []
    for start, end in zip(starts, ends):
        rows.append(
            {
                "network_id": job.network_id,
                "station_id": job.station_id,
                "provider": job.provider,
                "start_date": series.index[start],
                "start_month": int(series.index[start].month),
                "start_doy": int(series.index[start].dayofyear),
                "length": int(end - start),
                "pre_anomaly_c": (
                    float(anomaly.iloc[max(0, start - FLANK_DAYS) : start].mean()) if start else float("nan")
                ),
                "post_anomaly_c": (
                    float(anomaly.iloc[end : end + FLANK_DAYS].mean()) if end < len(series) else float("nan")
                ),
                "station_anomaly_sd_c": float(anomaly.std()),
            }
        )
    return rows


def _collect(worker, jobs: list[StationJob], workers: int) -> pd.DataFrame:
    rows: list[dict] = []
    if workers <= 1:
        for job in jobs:
            rows.extend(worker(job))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for block in pool.map(worker, jobs, chunksize=4):
                rows.extend(block)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    sort_key = [c for c in ("network_id", "station_id", "year", "start_date") if c in frame.columns]
    return frame.sort_values(sort_key).reset_index(drop=True)


def archive_station_years(workers: int = 8) -> pd.DataFrame:
    return _collect(station_year_rows, station_jobs(), workers)


def real_gaps(workers: int = 8) -> pd.DataFrame:
    return _collect(gap_rows, station_jobs(), workers)


def iter_station_series() -> Iterator[tuple[StationJob, pd.Series]]:
    for job in station_jobs():
        series = _trimmed_series(job)
        if series is not None:
            yield job, series
