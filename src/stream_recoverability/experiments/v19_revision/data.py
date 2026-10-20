"""Station-scoped forcing reads with the existing station-then-network semantics."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def station_air_series(path: Path, network_id: str, station_id: str, index: pd.DatetimeIndex) -> pd.Series | None:
    if not path.exists():
        return None
    columns = ["date", "air_temperature_c"]
    station = pq.read_table(path, columns=columns, filters=[("station_id", "=", str(station_id))], use_threads=False).to_pandas()
    if station.empty:
        station = pq.read_table(path, columns=columns, filters=[("network_id", "=", str(network_id))], use_threads=False).to_pandas()
        if station.empty:
            return None
        station = station.groupby("date", as_index=False).air_temperature_c.mean()
    series = pd.Series(pd.to_numeric(station.air_temperature_c, errors="coerce").to_numpy(), index=pd.to_datetime(station.date).to_numpy())
    series = series.loc[~series.index.duplicated(keep="first")].sort_index()
    return series.reindex(index)
