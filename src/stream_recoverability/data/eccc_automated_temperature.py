"""Official ECCC automated freshwater-quality temperature acquisition."""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

DIRECTORY = "/substances/monitor/automated-fresh-water-quality-monitoring-and-surveillance-data/"
CONTENTS_API = "https://data-donnees.az.ec.gc.ca/api/path_contents"
FILE_API = "https://data-donnees.az.ec.gc.ca/api/file"
STATIONS_FILE = "auto-water-qual-eau-stations.csv"
WATER_TEMPERATURE_CODE = 4730


def file_url(path: str) -> str:
    return FILE_API + "?" + urllib.parse.urlencode({"path": path})


def get_bytes(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "stream-recoverability-eccc-automated/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def directory_inventory() -> tuple[dict[str, object], ...]:
    url = CONTENTS_API + "?" + urllib.parse.urlencode({"path": DIRECTORY})
    return tuple(json.loads(get_bytes(url))["path_contents"])


def station_file_map(
    inventory: Sequence[Mapping[str, object]],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for item in inventory:
        name = str(item["name"])
        match = re.match(
            r"auto-water-qual-eau-([A-Z]{2}\d+[A-Z]+\d+)[-_].*\.(csv|xlsx)$",
            name,
            flags=re.IGNORECASE,
        )
        if match is not None:
            grouped.setdefault(match.group(1), []).append(str(item["path"]))
    return {key: tuple(sorted(value)) for key, value in grouped.items()}


def read_station_catalog(inventory: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    item = next(value for value in inventory if value["name"] == STATIONS_FILE)
    table = pd.read_csv(
        io.BytesIO(get_bytes(file_url(str(item["path"])))),
        dtype={"STATION_NO": str},
        encoding="cp1252",
    )
    for column in ("STATION_NAME", "PEARSEDA", "OCEANDA"):
        table[column] = table[column].astype(str).str.replace("�", "-", regex=False)
    return table


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def candidate_networks(
    stations: pd.DataFrame,
    files: Mapping[str, Sequence[str]],
) -> pd.DataFrame:
    available = stations.loc[stations["STATION_NO"].isin(files)].copy()
    rows = []
    for system, group in available.groupby("PEARSEDA", sort=True):
        if len(group) < 3:
            continue
        rows.append(
            {
                "network_id": f"eccc_automated_{_slug(str(system))}",
                "provider": "eccc_automated",
                "domain": "canada",
                "river_group": str(system),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["STATION_NO"].astype(str))),
                "latitude": float(group["LATITUDE"].mean()),
                "longitude": float(group["LONGITUDE"].mean()),
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows).sort_values("network_id").reset_index(drop=True)


def _temperature_rows(table: pd.DataFrame, site_id: str) -> pd.DataFrame:
    code = pd.to_numeric(table["VMV_CODE"], errors="coerce")
    selected = table.loc[
        code.eq(WATER_TEMPERATURE_CODE)
        & table["STATUS_STATUT"].astype(str).eq("V")
    ].copy()
    selected["date"] = pd.to_datetime(
        selected["DATE_TIME_HEURE"], format="mixed", dayfirst=True
    ).dt.normalize()
    selected["temperature_c"] = pd.to_numeric(selected["VALUE_VALEUR"])
    selected["site_id"] = str(site_id)
    selected["qualifier"] = "A"
    selected["provider_quality_status"] = "V"
    return selected[
        [
            "site_id",
            "date",
            "temperature_c",
            "qualifier",
            "provider_quality_status",
        ]
    ]


def parse_csv(payload: bytes, site_id: str) -> pd.DataFrame:
    frames = [
        _temperature_rows(chunk, site_id)
        for chunk in pd.read_csv(
            io.BytesIO(payload), chunksize=200_000, encoding="cp1252"
        )
    ]
    populated = [frame for frame in frames if not frame.empty]
    return (
        pd.concat(populated, ignore_index=True)
        if populated
        else pd.DataFrame(
            columns=[
                "site_id",
                "date",
                "temperature_c",
                "qualifier",
                "provider_quality_status",
            ]
        )
    )


def parse_excel(payload: bytes, site_id: str) -> pd.DataFrame:
    return _temperature_rows(pd.read_excel(io.BytesIO(payload)), site_id)


def daily_mean(frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
    populated = [frame for frame in frames if not frame.empty]
    hourly = pd.concat(populated, ignore_index=True)
    return (
        hourly.groupby(["site_id", "date"], as_index=False)
        .agg(
            temperature_c=("temperature_c", "mean"),
            hourly_observations=("temperature_c", "size"),
            qualifier=("qualifier", "first"),
            provider_quality_status=("provider_quality_status", "first"),
        )
        .sort_values(["site_id", "date"])
        .reset_index(drop=True)
    )


def download_station(site_id: str, paths: Sequence[str]) -> pd.DataFrame:
    frames = []
    for path in paths:
        payload = get_bytes(file_url(path))
        frames.append(
            parse_excel(payload, site_id)
            if path.lower().endswith(".xlsx")
            else parse_csv(payload, site_id)
        )
    return daily_mean(frames)


def download_stations(
    files: Mapping[str, Sequence[str]],
    station_ids: Sequence[str],
    output_root: str | Path,
    *,
    workers: int = 4,
    downloader: Callable[[str, Sequence[str]], pd.DataFrame] = download_station,
) -> dict[str, pd.DataFrame]:
    selected = tuple(sorted(str(value) for value in station_ids))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        downloaded = list(
            executor.map(lambda site_id: downloader(site_id, files[site_id]), selected)
        )
    output = Path(output_root)
    frames = {}
    for site_id, daily in zip(selected, downloaded, strict=True):
        directory = output / "stations" / site_id
        directory.mkdir(parents=True, exist_ok=True)
        daily.to_csv(directory / "daily_temperature.csv", index=False)
        pd.DataFrame(
            [
                {
                    "site_id": site_id,
                    "n_source_files": len(files[site_id]),
                    "n_daily_rows": len(daily),
                    "start": daily["date"].min().strftime("%Y-%m-%d"),
                    "end": daily["date"].max().strftime("%Y-%m-%d"),
                }
            ]
        ).to_csv(directory / "station_summary.csv", index=False)
        frames[site_id] = daily
    return frames


__all__ = [
    "candidate_networks",
    "daily_mean",
    "directory_inventory",
    "download_station",
    "download_stations",
    "file_url",
    "parse_csv",
    "parse_excel",
    "read_station_catalog",
    "station_file_map",
]
