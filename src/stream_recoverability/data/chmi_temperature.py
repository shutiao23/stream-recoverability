"""Official Czech CHMI historical measured water-temperature acquisition."""

from __future__ import annotations

import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

DATA_ROOT = "https://opendata.chmi.cz/hydrology/historical/data/measured_temperature"
INDEX_URL = f"{DATA_ROOT}/"
METADATA_URL = "https://opendata.chmi.cz/hydrology/historical/metadata/meta1.json"


def get_bytes(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "stream-recoverability-chmi/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def file_inventory() -> pd.DataFrame:
    document = get_bytes(INDEX_URL).decode("utf-8")
    rows = []
    for name in re.findall(r'href="([^"]+\.json)"', document):
        match = re.fullmatch(r"H_(.+)_OT_(\d{4})\.json", html.unescape(name))
        if match is not None:
            rows.append(
                {
                    "site_id": match.group(1),
                    "year": int(match.group(2)),
                    "file_name": name,
                }
            )
    return pd.DataFrame(rows).sort_values(["site_id", "year"]).reset_index(drop=True)


def station_catalog() -> pd.DataFrame:
    document = json.loads(get_bytes(METADATA_URL))
    table = document["data"]["data"]
    frame = pd.DataFrame(table["values"], columns=table["header"].split(","))
    return frame.rename(
        columns={
            "objID": "site_id",
            "STATION_NAME": "station_name",
            "STREAM_NAME": "river",
            "GEOGR1": "latitude",
            "GEOGR2": "longitude",
            "HLGP4": "basin_code",
        }
    )[
        [
            "site_id",
            "station_name",
            "river",
            "latitude",
            "longitude",
            "basin_code",
        ]
    ]


def _slug(value: str) -> str:
    translated = (
        value.lower()
        .replace("á", "a")
        .replace("č", "c")
        .replace("ď", "d")
        .replace("é", "e")
        .replace("ě", "e")
        .replace("í", "i")
        .replace("ň", "n")
        .replace("ó", "o")
        .replace("ř", "r")
        .replace("š", "s")
        .replace("ť", "t")
        .replace("ú", "u")
        .replace("ů", "u")
        .replace("ý", "y")
        .replace("ž", "z")
    )
    return re.sub(r"[^a-z0-9]+", "_", translated).strip("_")


def candidate_plan(
    catalog: pd.DataFrame,
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, tuple[str, ...]]]:
    years = {
        site_id: set(group["year"].astype(int))
        for site_id, group in inventory.groupby("site_id")
    }
    files = {
        (row.site_id, int(row.year)): row.file_name
        for row in inventory.itertuples(index=False)
    }
    available = catalog.loc[catalog["site_id"].isin(years)].copy()
    candidates = []
    station_files: dict[str, tuple[str, ...]] = {}
    for river, group in available.groupby("river", sort=True):
        selected = [
            site_id
            for site_id in group["site_id"].astype(str)
            if len(years[site_id]) >= 8
        ]
        while len(selected) >= 3:
            common = set.intersection(*(years[site_id] for site_id in selected))
            if len(common) >= 8:
                break
            choices = []
            for site_id in selected:
                remaining = [value for value in selected if value != site_id]
                overlap = set.intersection(*(years[value] for value in remaining))
                choices.append((len(overlap), -len(years[site_id]), site_id))
            selected.remove(max(choices)[2])
        if len(selected) < 3:
            continue
        common = sorted(set.intersection(*(years[site_id] for site_id in selected)))
        subset = group.loc[group["site_id"].isin(selected)]
        candidates.append(
            {
                "network_id": f"chmi_{_slug(str(river))}",
                "provider": "chmi",
                "domain": "czechia",
                "river_group": str(river),
                "n_catalog_stations": len(subset),
                "site_ids": "|".join(sorted(selected)),
                "latitude": float(subset["latitude"].mean()),
                "longitude": float(subset["longitude"].mean()),
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
                "n_common_file_years": len(common),
                "common_start_year": min(common),
                "common_end_year": max(common),
            }
        )
        for site_id in selected:
            station_files[site_id] = tuple(files[(site_id, year)] for year in common)
    return (
        pd.DataFrame(candidates).sort_values("network_id").reset_index(drop=True),
        station_files,
    )


def parse_year(payload: bytes, site_id: str) -> pd.DataFrame:
    document = json.loads(payload)
    frames = []
    for series in document["tsList"]:
        if series.get("tsConID") != "TO" or series.get("unit") != "0C":
            continue
        values = series["tsData"]["data"]["values"]
        frame = pd.DataFrame(values, columns=["date_time", "temperature_c"])
        frame["site_id"] = str(site_id)
        frame["date_time"] = pd.to_datetime(frame["date_time"], utc=True)
        frame["temperature_c"] = pd.to_numeric(frame["temperature_c"])
        frames.append(
            frame[["site_id", "date_time", "temperature_c"]]
        )
    return pd.concat(frames, ignore_index=True)


def download_station(site_id: str, files: Sequence[str]) -> pd.DataFrame:
    hourly = pd.concat(
        [parse_year(get_bytes(f"{DATA_ROOT}/{name}"), site_id) for name in files],
        ignore_index=True,
    )
    hourly["date"] = (
        pd.to_datetime(hourly["date_time"], utc=True)
        .dt.tz_convert("Europe/Prague")
        .dt.normalize()
        .dt.tz_localize(None)
    )
    return (
        hourly.groupby(["site_id", "date"], as_index=False)
        .agg(
            temperature_c=("temperature_c", "mean"),
            hourly_observations=("temperature_c", "size"),
        )
        .assign(
            provider_quality_status="published_historical",
            qualifier="A",
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def download_stations(
    station_files: Mapping[str, Sequence[str]],
    output_root: str | Path,
    *,
    workers: int = 20,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    selected = tuple(sorted(station_files))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        downloaded = list(
            executor.map(
                lambda site_id: download_station(site_id, station_files[site_id]),
                selected,
            )
        )
    output = Path(output_root)
    frames = {}
    summaries = []
    for site_id, daily in zip(selected, downloaded, strict=True):
        directory = output / "stations" / site_id
        directory.mkdir(parents=True, exist_ok=True)
        daily.to_csv(directory / "daily_temperature.csv", index=False)
        annual = daily.groupby(pd.to_datetime(daily["date"]).dt.year).size()
        row = {
            "site_id": site_id,
            "n_source_files": len(station_files[site_id]),
            "n_daily_rows": len(daily),
            "start": daily["date"].min(),
            "end": daily["date"].max(),
            "years_with_300_days": int(annual.ge(300).sum()),
        }
        pd.DataFrame([row]).to_csv(directory / "station_summary.csv", index=False)
        frames[site_id] = daily
        summaries.append(row)
    return frames, pd.DataFrame(summaries)


__all__ = [
    "candidate_plan",
    "download_stations",
    "file_inventory",
    "parse_year",
    "station_catalog",
]
