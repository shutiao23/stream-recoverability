"""Additive NASA POWER Rs rebuild for the internal Jinsha panel.

Hydro and CMA/GSOD columns are not edited. Sunshine ``DH`` remains in the
table as a sensitivity-only channel. The rebuild names hashes after the
files are written; it does not invent SHA-256 values.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NASA_POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
HTTP_USER_AGENT = "stream-recoverability-internal-rs/1.0"
RS_PROVIDER_CODE = "ALLSKY_SFC_SW_DWN"
RS_UNIT = "MJ/m^2/day"
RS_INTERPRETATION = "nasa_power_allsky_sfc_sw_dwn_mj_per_m2_per_day"
DEFAULT_START = "2006-01-01"
DEFAULT_END = "2020-12-31"
DEFAULT_COMMUNITY = "AG"
DEFAULT_TIME_STANDARD = "UTC"
HYDRO_INVARIANT_VARIABLES = ("T", "F", "L", "Ta", "P", "W", "RH", "DH")

Fetcher = Callable[[str, Mapping[str, str]], tuple[int, bytes, str]]


def _build_url(
    longitude: float,
    latitude: float,
    *,
    start: str,
    end: str,
    community: str,
    time_standard: str,
) -> str:
    query = (
        ("parameters", RS_PROVIDER_CODE),
        ("community", community),
        ("longitude", repr(float(longitude))),
        ("latitude", repr(float(latitude))),
        ("start", start.replace("-", "")),
        ("end", end.replace("-", "")),
        ("format", "JSON"),
        ("time-standard", time_standard),
    )
    return f"{NASA_POWER_DAILY_POINT_URL}?{urllib.parse.urlencode(query, safe=',/')}"


def urlopen_fetcher(url: str, headers: Mapping[str, str]) -> tuple[int, bytes, str]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return int(response.status), response.read(), str(response.url)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"NASA POWER HTTP {error.code} for {url}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"NASA POWER request failed for {url}") from error


def load_station_coordinates(path: str | Path) -> dict[str, tuple[float, float]]:
    frame = pd.read_csv(path)
    required = {"station_id", "latitude", "longitude"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise KeyError(f"station metadata missing {missing}")
    coordinates: dict[str, tuple[float, float]] = {}
    for row in frame.itertuples(index=False):
        station = str(row.station_id)
        latitude = float(row.latitude)
        longitude = float(row.longitude)
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise ValueError(f"non-finite coordinates for {station}")
        coordinates[station] = (longitude, latitude)
    return coordinates


def parse_power_rs_response(
    payload: Any,
    *,
    start: str,
    end: str,
    time_standard: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("type") != "Feature":
        raise TypeError("NASA POWER response must be a Feature")
    header = payload.get("header")
    parameters = payload.get("parameters")
    properties = payload.get("properties")
    geometry = payload.get("geometry")
    if not all(isinstance(value, Mapping) for value in (header, parameters, properties, geometry)):
        raise TypeError("NASA POWER response metadata fields must be mappings")
    expected_header = {
        "time_standard": time_standard,
        "start": start.replace("-", ""),
        "end": end.replace("-", ""),
    }
    for key, expected in expected_header.items():
        if header.get(key) != expected:
            raise ValueError(f"NASA POWER header {key} mismatch")
    fill_value = header.get("fill_value")
    if not isinstance(fill_value, (int, float)) or not math.isfinite(float(fill_value)):
        raise ValueError("NASA POWER header has no finite fill_value")
    if geometry.get("type") != "Point":
        raise ValueError("NASA POWER geometry must be Point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("NASA POWER geometry has no point coordinates")
    response_longitude, response_latitude = float(coordinates[0]), float(coordinates[1])
    parameter_metadata = parameters.get(RS_PROVIDER_CODE)
    parameter_values = properties.get("parameter")
    if not isinstance(parameter_values, Mapping):
        raise TypeError("NASA POWER properties.parameter must be a mapping")
    values = parameter_values.get(RS_PROVIDER_CODE)
    if not isinstance(parameter_metadata, Mapping) or not isinstance(values, Mapping):
        raise TypeError("NASA POWER Rs parameter metadata and values must be mappings")
    if parameter_metadata.get("units") != RS_UNIT:
        raise ValueError(
            f"NASA POWER unit mismatch for {RS_PROVIDER_CODE}: "
            f"{parameter_metadata.get('units')!r}"
        )
    rows: list[dict[str, Any]] = []
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    for date_text, raw_value in values.items():
        date = pd.to_datetime(str(date_text), format="%Y%m%d").normalize()
        if not start_ts <= date <= end_ts:
            raise ValueError("NASA POWER returned a date outside the rebuild period")
        numeric = pd.to_numeric(raw_value, errors="coerce")
        if not np.isfinite(numeric):
            raise ValueError("NASA POWER daily value is non-numeric")
        available = not math.isclose(
            float(numeric), float(fill_value), rel_tol=0.0, abs_tol=0.0
        )
        rows.append(
            {
                "date": date,
                "value": float(numeric) if available else np.nan,
                "raw_value": float(numeric),
                "natural_observed": available,
                "quality_approved": available,
                "qc_status": "provider_value" if available else "provider_fill_value",
                "response_longitude": response_longitude,
                "response_latitude": response_latitude,
            }
        )
    observations = pd.DataFrame(rows)
    if observations["date"].duplicated().any():
        raise ValueError("NASA POWER Rs response contains duplicate dates")
    metadata = {
        "time_standard": header.get("time_standard"),
        "fill_value": float(fill_value),
        "response_longitude": response_longitude,
        "response_latitude": response_latitude,
        "n_days": int(len(observations)),
        "n_finite": int(observations["quality_approved"].sum()),
    }
    return observations.sort_values("date").reset_index(drop=True), metadata


def fetch_station_rs(
    station_id: str,
    longitude: float,
    latitude: float,
    *,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    community: str = DEFAULT_COMMUNITY,
    time_standard: str = DEFAULT_TIME_STANDARD,
    fetcher: Fetcher = urlopen_fetcher,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    url = _build_url(
        longitude,
        latitude,
        start=start,
        end=end,
        community=community,
        time_standard=time_standard,
    )
    status, body, final_url = fetcher(
        url,
        {"Accept": "application/json", "User-Agent": HTTP_USER_AGENT},
    )
    if status != 200:
        raise RuntimeError(f"NASA POWER status {status} for {station_id}")
    payload = json.loads(body.decode("utf-8"))
    observations, metadata = parse_power_rs_response(
        payload, start=start, end=end, time_standard=time_standard
    )
    metadata.update(
        {
            "station_id": station_id,
            "requested_longitude": float(longitude),
            "requested_latitude": float(latitude),
            "url": url,
            "final_url": final_url,
        }
    )
    observations["station_id"] = station_id
    return observations, metadata


def merge_rs_into_long(
    long_data: pd.DataFrame,
    rs_observations: pd.DataFrame,
) -> pd.DataFrame:
    """Append Rs rows. Existing hydro/CMA rows are copied unchanged."""

    if "Rs" in set(long_data["variable"].astype(str)):
        raise ValueError("source long already contains Rs; refusing a second merge")
    template = long_data.loc[long_data["variable"].eq("Ta")].copy()
    if template.empty:
        raise ValueError("source long has no Ta rows to copy calendar/split from")
    merged_rs = template.merge(
        rs_observations,
        on=["date", "station_id"],
        how="left",
        suffixes=("", "_rs"),
        validate="one_to_one",
    )
    merged_rs["variable"] = "Rs"
    merged_rs["raw_name"] = RS_PROVIDER_CODE
    merged_rs["raw_unit"] = RS_UNIT
    merged_rs["unit"] = RS_UNIT
    merged_rs["source"] = "nasa_power_daily_point"
    merged_rs["value"] = merged_rs["value_rs"]
    merged_rs["raw_value"] = merged_rs["raw_value_rs"]
    merged_rs["natural_observed"] = merged_rs["natural_observed_rs"].fillna(False)
    merged_rs["quality_approved"] = merged_rs["quality_approved_rs"].fillna(False)
    merged_rs["qc_status"] = merged_rs["qc_status_rs"].fillna("provider_missing")
    extra = [column for column in merged_rs.columns if column.endswith("_rs")]
    merged_rs = merged_rs.drop(columns=extra)
    return pd.concat([long_data, merged_rs[long_data.columns]], ignore_index=True)


def assert_hydro_invariants(before: pd.DataFrame, after: pd.DataFrame) -> None:
    keys = ["date", "station_id", "variable"]
    before_hydro = before.loc[before["variable"].isin(HYDRO_INVARIANT_VARIABLES)]
    after_hydro = after.loc[after["variable"].isin(HYDRO_INVARIANT_VARIABLES)]
    left = before_hydro.sort_values(keys).reset_index(drop=True)
    right = after_hydro.sort_values(keys).reset_index(drop=True)
    if len(left) != len(right):
        raise ValueError("Rs merge changed the hydro/CMA row count")
    pd.testing.assert_frame_equal(
        left[keys + ["value", "raw_value", "quality_approved", "natural_observed"]],
        right[keys + ["value", "raw_value", "quality_approved", "natural_observed"]],
        check_dtype=False,
    )


def rebuild_internal_rs_panel(
    long_data: pd.DataFrame,
    station_metadata_path: str | Path,
    *,
    stations: Sequence[str] = ("B1", "S2", "P3"),
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    fetcher: Fetcher = urlopen_fetcher,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    coordinates = load_station_coordinates(station_metadata_path)
    rs_frames: list[pd.DataFrame] = []
    station_reports: list[dict[str, Any]] = []
    for station in stations:
        if station not in coordinates:
            raise KeyError(f"station metadata has no coordinates for {station}")
        longitude, latitude = coordinates[station]
        observations, metadata = fetch_station_rs(
            station,
            longitude,
            latitude,
            start=start,
            end=end,
            fetcher=fetcher,
        )
        rs_frames.append(observations)
        station_reports.append(metadata)
    rs_observations = pd.concat(rs_frames, ignore_index=True)
    merged = merge_rs_into_long(long_data, rs_observations)
    assert_hydro_invariants(long_data, merged)
    report = {
        "schema_version": "internal_nasa_rs_rebuild_v1",
        "start": start,
        "end": end,
        "community": DEFAULT_COMMUNITY,
        "time_standard": DEFAULT_TIME_STANDARD,
        "provider_code": RS_PROVIDER_CODE,
        "interpretation": RS_INTERPRETATION,
        "stations": station_reports,
        "source_long_rows": int(len(long_data)),
        "rebuilt_long_rows": int(len(merged)),
        "rs_rows": int(merged["variable"].eq("Rs").sum()),
    }
    return merged, report


__all__ = [
    "RS_INTERPRETATION",
    "RS_PROVIDER_CODE",
    "assert_hydro_invariants",
    "fetch_station_rs",
    "load_station_coordinates",
    "merge_rs_into_long",
    "parse_power_rs_response",
    "rebuild_internal_rs_panel",
    "urlopen_fetcher",
]
