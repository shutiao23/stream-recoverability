"""NVE HydAPI daily river-temperature acquisition for confirmation two."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Sequence

import pandas as pd

SILDRE = "https://sildre.nve.no/list?lang=en"
HYDAPI = "https://hydapi.nve.no/api/v1"
USER_AGENT = "stream-recoverability/1.1 second-confirmation"


def _bytes(url: str, *, api_key: str | None = None, timeout: int = 120) -> bytes:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json" if api_key is not None else "*/*",
    }
    if api_key is not None:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def discover_public_hydapi_key() -> str:
    """Read the current public-client key from NVE's official Sildre bundle."""

    html = _bytes(SILDRE).decode("utf-8")
    match = re.search(r'src="(/js/app\.[^"]+\.js)"', html)
    if match is None:
        raise ValueError("Sildre application bundle was not discoverable")
    bundle = _bytes("https://sildre.nve.no" + match.group(1)).decode("utf-8")
    key = re.search(r'hydApiKey:"([^"]+)"', bundle)
    if key is None:
        raise ValueError("Sildre public HydAPI client key was not discoverable")
    return key.group(1)


def series_catalog(api_key: str) -> pd.DataFrame:
    """Return measured river series with a daily mean resolution."""

    url = HYDAPI + "/Series?" + urllib.parse.urlencode({"Parameter": 1003})
    document = json.loads(_bytes(url, api_key=api_key))
    rows = []
    for series in document["data"]:
        daily = next(
            (
                item
                for item in series.get("resolutionList") or []
                if int(item.get("resTime") or -1) == 1440
            ),
            None,
        )
        if daily is None:
            continue
        if not str(series.get("measuredOrDerived") or "").lower().startswith("målt"):
            continue
        if not str(series.get("observationPlace") or "").lower().startswith("elv"):
            continue
        station = str(series["stationId"])
        rows.append(
            {
                "site_id": station,
                "station_name": series.get("stationName"),
                "basin_id": station.split(".")[0],
                "latitude": series.get("latitude"),
                "longitude": series.get("longitude"),
                "county": series.get("countyName"),
                "daily_start": pd.to_datetime(daily["dataFromTime"]),
                "daily_end": pd.to_datetime(daily["dataToTime"]),
                "unit": series.get("unit"),
                "measured_or_derived": series.get("measuredOrDerived"),
                "observation_place": series.get("observationPlace"),
            }
        )
    return pd.DataFrame(rows)


def _common_subset(frame: pd.DataFrame, *, minimum_years: float = 8.0) -> pd.DataFrame:
    selected = frame.copy()
    while len(selected) >= 3:
        years = (selected["daily_end"].min() - selected["daily_start"].max()).days / 365.25
        if years >= minimum_years:
            return selected.sort_values("site_id")
        limiting = {selected["daily_start"].idxmax(), selected["daily_end"].idxmin()}
        choices = []
        for index in limiting:
            reduced = selected.drop(index)
            span = (reduced["daily_end"].min() - reduced["daily_start"].max()).days
            choices.append((span, str(selected.loc[index, "site_id"]), index))
        selected = selected.drop(max(choices)[2])
    return selected.iloc[0:0]


def candidate_networks(
    catalog: pd.DataFrame, *, maximum_stations: int = 8
) -> pd.DataFrame:
    """Group station IDs by NVE drainage-basin identifier."""

    rows = []
    for basin, group in catalog.groupby("basin_id"):
        selected = _common_subset(group)
        if len(selected) < 3:
            continue
        if len(selected) > maximum_stations:
            selected = (
                selected.assign(
                    _span=(selected["daily_end"] - selected["daily_start"]).dt.days
                )
                .sort_values(["_span", "site_id"], ascending=[False, True])
                .head(maximum_stations)
                .drop(columns="_span")
                .sort_values("site_id")
            )
        start = selected["daily_start"].max()
        end = selected["daily_end"].min()
        # Twelve years are enough for the nested fit/evaluation design and
        # avoid oversized observation responses for very long archives.
        request_start = max(start, end - pd.DateOffset(years=12))
        rows.append(
            {
                "network_id": f"nve_basin_{basin}",
                "provider": "nve_hydapi",
                "domain": "norway",
                "river_group": f"NVE drainage basin {basin}",
                "n_catalog_stations": len(selected),
                "site_ids": "|".join(selected["site_id"].astype(str)),
                "latitude": float(selected["latitude"].mean()),
                "longitude": float(selected["longitude"].mean()),
                "catalog_common_start": request_start.strftime("%Y-%m-%d"),
                "catalog_common_end": end.strftime("%Y-%m-%d"),
                "catalog_common_years": float((end - request_start).days / 365.25),
                "prior_temperature_values_seen": False,
                "candidate_status": "new_metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["n_catalog_stations", "network_id"], ascending=[False, True]
    )


def observations(
    api_key: str,
    stations: Sequence[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """Download controlled, uncorrected daily means for several stations."""

    url = HYDAPI + "/Observations?" + urllib.parse.urlencode(
        {
            "StationId": ",".join(map(str, stations)),
            "Parameter": 1003,
            "ResolutionTime": 1440,
            "ReferenceTime": f"{start}/{end}",
        }
    )
    document = json.loads(_bytes(url, api_key=api_key, timeout=180))
    rows = []
    for series in document["data"]:
        station = str(series["stationId"])
        for item in series.get("observations") or []:
            quality = int(item.get("quality") or 0)
            correction = int(item.get("correction") or 0)
            if quality < 2 or correction != 0:
                continue
            rows.append(
                {
                    "site_id": station,
                    "date": pd.to_datetime(item["time"], utc=True)
                    .tz_localize(None)
                    .normalize(),
                    "temperature_c": item["value"],
                    "qualifier": "A",
                    "provider_quality_code": quality,
                    "provider_correction_code": correction,
                }
            )
    return pd.DataFrame(rows)


__all__ = [
    "candidate_networks",
    "discover_public_hydapi_key",
    "observations",
    "series_catalog",
]
