"""Step 1 — evaluation population, truth, and the pre-declared network split.

The population is river waterbodies with fully observed calendar years, taken
from the frozen `step1_universe` roster. Reference series are never imputed.
Unlike the v16 programme, the split is declared at the network level and is
stratified on provider and donor regime, so that development and reserved
networks are exchangeable on the covariate the design conditions on.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.paths import (
    AIR_FORCING,
    FIRST_PANEL_ROOT,
    MIN_COMPLETE_YEARS,
    NETWORK_ROSTER,
    RESERVED_NETWORK_FRACTION,
    SECOND_PANEL_ROOT,
    SPLIT_SEED,
    TRUSTED_YEARS,
    donor_regime,
)


@dataclass(frozen=True)
class StationRecord:
    """Everything one station contributes to the study."""

    network_id: str
    station_id: str
    provider: str
    daily: pd.DataFrame          # full network panel, daily index, station columns
    donors: tuple[str, ...]      # other stations in the same network
    complete_years: tuple[int, ...]
    regulation_status: str

    @property
    def target(self) -> pd.Series:
        return pd.to_numeric(self.daily[self.station_id], errors="coerce")


def network_directory(source_root: str):
    return FIRST_PANEL_ROOT if str(source_root) == "first" else SECOND_PANEL_ROOT


@lru_cache(maxsize=None)
def load_network_panel(network_id: str, source_root: str) -> pd.DataFrame:
    path = network_directory(source_root) / str(network_id) / "daily_wide_temperature.csv"
    panel = read_temperature_panel(str(path))
    panel.columns = [str(column) for column in panel.columns]
    return panel


def trusted_years() -> pd.DataFrame:
    frame = pd.read_csv(TRUSTED_YEARS)
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["year"] = frame["year"].astype(int)
    return frame.loc[frame["eligible_annual_truth"].astype(bool)].copy()


def network_roster() -> pd.DataFrame:
    frame = pd.read_csv(NETWORK_ROSTER)
    frame["network_id"] = frame["network_id"].astype(str)
    return frame


@lru_cache(maxsize=1)
def air_forcing() -> pd.DataFrame:
    if not AIR_FORCING.exists():
        return pd.DataFrame(columns=["date", "station_id", "air_temperature_c", "network_id"])
    frame = pd.read_parquet(AIR_FORCING)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["network_id"] = frame["network_id"].astype(str)
    return frame


@lru_cache(maxsize=1)
def _air_series_by_key() -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """Air forcing split into per-station and per-network series, built once.

    The v18 forcing table covers every station in the panel and is two orders
    of magnitude larger than the one v17 shipped with. Scanning it with a
    per-call ``astype(str)`` materialised the whole column on every lookup,
    which was affordable when 2% of stations had forcing and is not when all of
    them do.
    """

    frame = air_forcing()
    if frame.empty:
        return {}, {}

    def to_series(block: pd.DataFrame) -> pd.Series:
        series = pd.Series(
            pd.to_numeric(block["air_temperature_c"], errors="coerce").to_numpy(dtype=float),
            index=pd.to_datetime(block["date"]).to_numpy(),
        )
        return series[~series.index.duplicated(keep="first")].sort_index()

    by_station = {str(key): to_series(block) for key, block in frame.groupby("station_id", observed=True)}
    by_network = {
        str(key): to_series(block.groupby("date", as_index=False)["air_temperature_c"].mean())
        for key, block in frame.groupby("network_id", observed=True)
    }
    return by_station, by_network


def air_series_for(network_id: str, station_id: str, index: pd.DatetimeIndex) -> pd.Series | None:
    by_station, by_network = _air_series_by_key()
    if not by_station and not by_network:
        return None
    series = by_station.get(str(station_id))
    if series is None:
        series = by_network.get(str(network_id))
    if series is None:
        return None
    return series.reindex(index)


def station_roster() -> pd.DataFrame:
    """One row per eligible station, with the covariates used for stratification."""

    years = trusted_years()
    networks = network_roster()[["network_id", "provider", "source_root", "regulation_status"]]
    counts = (
        years.groupby(["network_id", "station_id"])
        .agg(
            n_complete_years=("year", "nunique"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            median_donors_full_year=("n_donors_full_year", "median"),
            median_donors_any=("n_donors_any", "median"),
            mean_hottest_30=("annual_hottest_30", "mean"),
            sd_hottest_30=("annual_hottest_30", "std"),
        )
        .reset_index()
    )
    roster = counts.merge(networks, on="network_id", how="left")
    roster["donor_regime"] = roster["median_donors_full_year"].fillna(0).map(donor_regime)
    roster["eligible_station"] = roster["n_complete_years"] >= MIN_COMPLETE_YEARS
    return roster


def network_strata(roster: pd.DataFrame) -> pd.DataFrame:
    """Network-level stratification key: provider x dominant donor regime."""

    eligible = roster.loc[roster["eligible_station"]].copy()
    grouped = (
        eligible.groupby("network_id")
        .agg(
            provider=("provider", "first"),
            source_root=("source_root", "first"),
            n_stations=("station_id", "nunique"),
            n_station_years=("n_complete_years", "sum"),
            median_donors=("median_donors_full_year", "median"),
        )
        .reset_index()
    )
    grouped["donor_regime"] = grouped["median_donors"].fillna(0).map(donor_regime)
    grouped["stratum"] = grouped["provider"].astype(str) + "|" + grouped["donor_regime"].astype(str)
    return grouped


def declare_split(
    strata: pd.DataFrame,
    *,
    seed: int = SPLIT_SEED,
    reserved_fraction: float = RESERVED_NETWORK_FRACTION,
) -> pd.DataFrame:
    """Stratified network-level split, fixed seed, declared before any scoring.

    Reserved networks are held for Step 10 and are never touched before it.
    """

    rng = np.random.default_rng(int(seed))
    assignment: list[str] = []
    frame = strata.sort_values(["stratum", "network_id"]).reset_index(drop=True)
    for _, block in frame.groupby("stratum", sort=True):
        ids = block["network_id"].tolist()
        order = rng.permutation(len(ids))
        n_reserved = int(np.floor(len(ids) * reserved_fraction))
        if len(ids) >= 3 and n_reserved == 0:
            n_reserved = 1
        reserved = {ids[int(i)] for i in order[:n_reserved]}
        for network_id in ids:
            assignment.append("reserved" if network_id in reserved else "development")
    frame["split_role"] = assignment
    return frame


def station_records(
    roster: pd.DataFrame,
    split: pd.DataFrame,
    *,
    split_role: str | None = None,
) -> Iterator[StationRecord]:
    """Yield one StationRecord per eligible station in the requested split role."""

    years = trusted_years()
    complete = years.groupby(["network_id", "station_id"])["year"].apply(
        lambda values: tuple(sorted(int(value) for value in values))
    )
    roles = split.set_index("network_id")["split_role"].to_dict()
    eligible = roster.loc[roster["eligible_station"]].copy()
    if split_role is not None:
        eligible = eligible.loc[eligible["network_id"].map(roles).eq(split_role)]
    for network_id, block in eligible.groupby("network_id", sort=True):
        source_root = str(block["source_root"].iloc[0])
        try:
            panel = load_network_panel(str(network_id), source_root)
        except (FileNotFoundError, ValueError):
            continue
        columns = [str(column) for column in panel.columns]
        for row in block.itertuples(index=False):
            station_id = str(row.station_id)
            if station_id not in columns:
                continue
            donors = tuple(name for name in columns if name != station_id)
            key = (str(network_id), station_id)
            if key not in complete.index:
                continue
            yield StationRecord(
                network_id=str(network_id),
                station_id=station_id,
                provider=str(row.provider),
                daily=panel,
                donors=donors,
                complete_years=tuple(complete.loc[key]),
                regulation_status=str(row.regulation_status),
            )


def station_jobs(roster: pd.DataFrame, split: pd.DataFrame, *, split_role: str | None = None) -> list[dict]:
    """Lightweight, picklable job descriptors for parallel case building."""

    years = trusted_years()
    complete = years.groupby(["network_id", "station_id"])["year"].apply(
        lambda values: tuple(sorted(int(value) for value in values))
    )
    roles = split.set_index("network_id")["split_role"].to_dict()
    eligible = roster.loc[roster["eligible_station"]].copy()
    if split_role is not None:
        eligible = eligible.loc[eligible["network_id"].map(roles).eq(split_role)]
    jobs: list[dict] = []
    for row in eligible.itertuples(index=False):
        key = (str(row.network_id), str(row.station_id))
        if key not in complete.index:
            continue
        jobs.append(
            {
                "network_id": str(row.network_id),
                "station_id": str(row.station_id),
                "provider": str(row.provider),
                "source_root": str(row.source_root),
                "regulation_status": str(row.regulation_status),
                "split_role": roles.get(str(row.network_id), "development"),
                "complete_years": tuple(complete.loc[key]),
            }
        )
    return jobs


def interannual_scale(roster: pd.DataFrame) -> dict[str, float]:
    """Natural scale of the endpoint: interannual SD of the annual peak."""

    eligible = roster.loc[roster["eligible_station"], "sd_hottest_30"].dropna()
    return {
        "n_stations": int(len(eligible)),
        "mean_sd_c": float(eligible.mean()),
        "median_sd_c": float(eligible.median()),
        "q25_sd_c": float(eligible.quantile(0.25)),
        "q75_sd_c": float(eligible.quantile(0.75)),
    }


def resolve_donors(daily: pd.DataFrame, station_id: str) -> tuple[str, ...]:
    return tuple(str(name) for name in daily.columns if str(name) != str(station_id))


def observed_complete_years(target: pd.Series, candidate_years: Sequence[int]) -> tuple[int, ...]:
    kept = []
    for year in candidate_years:
        block = target.loc[target.index.year == int(year)]
        if len(block) and bool(block.notna().all()):
            kept.append(int(year))
    return tuple(kept)
