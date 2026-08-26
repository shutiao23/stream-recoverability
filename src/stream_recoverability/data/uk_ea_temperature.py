"""UK EA hydrology temperature readings, resampled to daily mean.

Sub-daily API values are not invented daily years. Loire/last-check are unused.
A name cluster is not T8 until 3 stations share ≥8 overlapping daily years.
"""

from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import get_json

EA_STATION = "https://environment.data.gov.uk/hydrology/id/stations/{station}.json"
EA_READINGS = "https://environment.data.gov.uk/hydrology/data/readings.json"


def station_temperature_measures(station_id: str) -> list[str]:
    url = EA_STATION.format(station=urllib.parse.quote(str(station_id), safe=""))
    document = get_json(url, timeout=60, retries=4)
    items = document.get("items") or [document]
    measures: list[str] = []
    for item in items:
        for measure in item.get("measures") or []:
            period = str(measure.get("period") or measure.get("unitName") or "")
            label = str(measure.get("label") or measure.get("parameter") or "").lower()
            observed = str(measure.get("observedProperty") or "").lower()
            href = measure.get("@id") or measure.get("notation")
            if href and ("temp" in label or "temp" in observed or "temp" in period.lower()):
                measures.append(str(href))
            elif href and measure.get("parameter") in {"temperature", "waterTemperature"}:
                measures.append(str(href))
    return list(dict.fromkeys(measures))


def readings_window(measure: str, start: str, end: str) -> list[dict[str, Any]]:
    rows = []
    offset = 0
    limit = 2000
    while True:
        url = EA_READINGS + "?" + urllib.parse.urlencode(
            {
                "measure": measure,
                "mineq-date": start,
                "max-date": end,
                "_limit": str(limit),
                "_offset": str(offset),
            }
        )
        document = get_json(url, timeout=90, retries=4)
        chunk = document.get("items") or []
        for item in chunk:
            rows.append(
                {
                    "date": item.get("dateTime") or item.get("date"),
                    "temperature_c": item.get("value"),
                }
            )
        if len(chunk) < limit:
            break
        offset += limit
        if offset > 200000:
            break
        time.sleep(0.05)
    return rows


def uk_ea_daily(
    station_id: str,
    *,
    cache_dir: str | Path,
    start: str = "2000-01-01",
    end: str = "2024-12-31",
) -> pd.DataFrame:
    """Derived daily mean from public sub-daily readings. Not invented years."""

    root = Path(cache_dir)
    dest = root / "uk_ea" / f"{station_id}_daily.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        frame = pd.read_csv(dest)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"])
            return frame
        dest.unlink()
    measures = station_temperature_measures(station_id)
    rows: list[dict[str, Any]] = []
    years = range(int(start[:4]), int(end[:4]) + 1)
    for measure in measures[:2]:
        for year in years:
            chunk_start = f"{year}-01-01"
            chunk_end = f"{year}-12-31"
            try:
                rows.extend(readings_window(measure, chunk_start, chunk_end))
            except Exception:
                continue
            time.sleep(0.1)
    raw = pd.DataFrame(rows)
    if raw.empty:
        return pd.DataFrame(columns=["site_id", "date", "temperature_c"])
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["temperature_c"] = pd.to_numeric(raw["temperature_c"], errors="coerce")
    raw = raw.dropna(subset=["date", "temperature_c"])
    daily = (
        raw.set_index("date")["temperature_c"]
        .resample("D")
        .mean()
        .rename("temperature_c")
        .reset_index()
    )
    daily["site_id"] = str(station_id)
    daily = daily.dropna(subset=["temperature_c"])
    if daily.empty:
        return daily
    daily.to_csv(dest, index=False)
    return daily


__all__ = ["station_temperature_measures", "uk_ea_daily"]
