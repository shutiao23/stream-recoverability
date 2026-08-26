"""Download public daily water temperature. Used after the catalog check."""

from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import get_json
from stream_recoverability.data.public_river_inventory import (
    DAILY_MEAN,
    TEMPERATURE,
    USGS_OGC,
)

CACHE = Path("data/public_rivers")


def usgs_daily_temperature(
    site_id: str,
    start: str,
    end: str,
    *,
    cache_dir: Path | None = None,
    pause_s: float = 0.1,
) -> pd.DataFrame:
    """Download USGS daily mean water temperature for one site."""

    root = CACHE if cache_dir is None else Path(cache_dir)
    dest = root / "usgs" / f"{site_id}_{start}_{end}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        frame = pd.read_csv(dest)
        frame["date"] = pd.to_datetime(frame["date"])
        return frame
    try:
        return _usgs_ogc_daily(site_id, start, end, dest, pause_s=pause_s)
    except RuntimeError as error:
        if "HTTP 429" not in str(error) and "HTTP 5" not in str(error):
            raise
        from stream_recoverability.data.nwis_temperature import nwis_daily_temperature

        return nwis_daily_temperature(site_id, start, end, cache_dir=root)


def _usgs_ogc_daily(
    site_id: str, start: str, end: str, dest: Path, *, pause_s: float
) -> pd.DataFrame:
    url = (
        f"{USGS_OGC}/daily/items?"
        + urllib.parse.urlencode(
            {
                "f": "json",
                "limit": "10000",
                "monitoring_location_id": f"USGS-{site_id}",
                "parameter_code": TEMPERATURE,
                "statistic_id": DAILY_MEAN,
                "datetime": f"{start}/{end}",
            }
        )
    )
    rows: list[dict[str, Any]] = []
    next_url: str | None = url
    pages = 0
    while next_url and pages < 50:
        document = get_json(next_url, timeout=60, retries=2, base_pause_s=1.0)
        pages += 1
        for feature in document.get("features") or []:
            props = feature.get("properties") or {}
            rows.append(
                {
                    "site_id": site_id,
                    "date": props.get("time") or props.get("datetime"),
                    "temperature_c": props.get("value"),
                    "qualifier": ",".join(props.get("qualifiers") or [])
                    if isinstance(props.get("qualifiers"), list)
                    else props.get("qualifiers"),
                }
            )
        next_url = None
        for link in document.get("links") or []:
            if link.get("rel") in {"next", "next-page"}:
                next_url = link.get("href")
                break
        time.sleep(pause_s)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce").dt.tz_localize(
            None
        ).dt.normalize()
        frame["temperature_c"] = pd.to_numeric(frame["temperature_c"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        frame.to_csv(dest, index=False)
    else:
        frame = pd.DataFrame(
            columns=["site_id", "date", "temperature_c", "qualifier"]
        )
        frame.to_csv(dest, index=False)
    return frame


def river_wide_panel(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """One date index, one column per site."""

    pieces = []
    for frame in frames:
        if frame.empty:
            continue
        piece = frame[["date", "temperature_c"]].copy()
        site = str(frame["site_id"].iloc[0])
        piece = piece.rename(columns={"temperature_c": site}).drop_duplicates("date")
        pieces.append(piece.set_index("date"))
    if not pieces:
        return pd.DataFrame()
    wide = pd.concat(pieces, axis=1).sort_index()
    return wide


def overlap_report(wide: pd.DataFrame, *, min_stations: int = 4) -> dict[str, Any]:
    if wide.empty:
        return {
            "n_days": 0,
            "n_stations": 0,
            "days_with_min_stations": 0,
            "overlap_start": None,
            "overlap_end": None,
            "overlap_years": 0.0,
            "complete_enough": False,
        }
    counts = wide.notna().sum(axis=1)
    good = counts.ge(min_stations)
    if not bool(good.any()):
        return {
            "n_days": int(len(wide)),
            "n_stations": int(wide.shape[1]),
            "days_with_min_stations": 0,
            "overlap_start": None,
            "overlap_end": None,
            "overlap_years": 0.0,
            "complete_enough": False,
        }
    start = wide.index[good].min()
    end = wide.index[good].max()
    years = float((end - start).days / 365.25)
    return {
        "n_days": int(len(wide)),
        "n_stations": int(wide.shape[1]),
        "days_with_min_stations": int(good.sum()),
        "overlap_start": pd.Timestamp(start).date().isoformat(),
        "overlap_end": pd.Timestamp(end).date().isoformat(),
        "overlap_years": years,
        "station_coverage": {
            column: float(wide[column].notna().mean()) for column in wide.columns
        },
        "complete_enough": bool(years >= 8 and int(good.sum()) >= 5 * 365),
    }


def missing_gap_catalog(wide: pd.DataFrame) -> pd.DataFrame:
    """Real missing blocks: consecutive days a station has no daily value."""

    rows = []
    for site in wide.columns:
        missing = wide[site].isna().to_numpy()
        if not missing.any():
            continue
        starts = []
        length = 0
        start_i = 0
        for index, flag in enumerate(missing):
            if flag:
                if length == 0:
                    start_i = index
                length += 1
            elif length:
                rows.append(
                    {
                        "site_id": site,
                        "start_date": pd.Timestamp(wide.index[start_i]).date().isoformat(),
                        "length_days": length,
                        "season": ("DJF", "MAM", "JJA", "SON")[
                            (pd.Timestamp(wide.index[start_i]).month % 12) // 3
                        ],
                    }
                )
                length = 0
        if length:
            rows.append(
                {
                    "site_id": site,
                    "start_date": pd.Timestamp(wide.index[start_i]).date().isoformat(),
                    "length_days": length,
                    "season": ("DJF", "MAM", "JJA", "SON")[
                        (pd.Timestamp(wide.index[start_i]).month % 12) // 3
                    ],
                }
            )
    return pd.DataFrame(rows)


__all__ = [
    "missing_gap_catalog",
    "overlap_report",
    "river_wide_panel",
    "usgs_daily_temperature",
]
