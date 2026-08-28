"""Official Finland SYKE surface-water-temperature OData acquisition."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import pandas as pd

ODATA = "https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.2/odata"


def get_json(url: str, timeout: int = 120) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "stream-recoverability-syke/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def station_catalog() -> pd.DataFrame:
    query = urllib.parse.urlencode({"$filter": "Suure_Id eq 11", "$top": 1000})
    document = get_json(f"{ODATA}/Paikka?{query}")
    rows = []
    for station in document["value"]:
        if station["Jarvi_Id"] is not None:
            continue
        rows.append(
            {
                "site_id": str(station["Paikka_Id"]),
                "station_number": station["Nro"],
                "station_name": str(station["Nimi"]).strip(),
                "subbasin": str(station["VesalNimi"] or "").strip(),
                "main_basin": str(station["PaaVesalNimi"] or "").strip(),
                "latitude": _coordinate(station["KoordLat"]),
                "longitude": _coordinate(station["KoordLong"]),
            }
        )
    return pd.DataFrame(rows).sort_values("site_id").reset_index(drop=True)


def _coordinate(value: object) -> float:
    text = str(value).strip().zfill(6)
    degrees = int(text[:-4])
    minutes = int(text[-4:-2])
    seconds = int(text[-2:])
    return degrees + minutes / 60 + seconds / 3600


def download_station(site_id: str) -> pd.DataFrame:
    query = urllib.parse.urlencode({"$filter": f"Paikka_Id eq {site_id}"})
    url: str | None = f"{ODATA}/LampoPintavesi?{query}"
    rows = []
    while url is not None:
        document = get_json(url)
        rows.extend(
            {
                "site_id": str(item["Paikka_Id"]),
                "date": pd.to_datetime(item["Aika"]),
                "temperature_c": float(item["Arvo"]),
                "provider_quality_status": "published_no_flag_field",
                "qualifier": "A",
            }
            for item in document["value"]
        )
        url = document.get("odata.nextLink")
    if not rows:
        return pd.DataFrame(
            columns=[
                "site_id",
                "date",
                "temperature_c",
                "provider_quality_status",
                "qualifier",
            ]
        )
    return (
        pd.DataFrame(rows)
        .groupby(["site_id", "date"], as_index=False)
        .agg(
            temperature_c=("temperature_c", "mean"),
            provider_quality_status=("provider_quality_status", "first"),
            qualifier=("qualifier", "first"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def _slug(value: str) -> str:
    translated = (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("å", "aa")
    )
    return re.sub(r"[^a-z0-9]+", "_", translated).strip("_")


def candidate_networks(catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    used: set[str] = set()
    for subbasin, group in catalog.groupby("subbasin", sort=True):
        if str(subbasin).strip() and len(group) >= 3:
            used.update(group["site_id"].astype(str))
            rows.append(_candidate(group, f"syke_subbasin_{_slug(subbasin)}", subbasin))
    remaining = catalog.loc[~catalog["site_id"].isin(used)]
    for basin, group in remaining.groupby("main_basin", sort=True):
        if str(basin).strip() and len(group) >= 3:
            used.update(group["site_id"].astype(str))
            rows.append(_candidate(group, f"syke_basin_{_slug(basin)}", basin))
    return pd.DataFrame(rows).sort_values("network_id").reset_index(drop=True)


def _candidate(group: pd.DataFrame, network_id: str, river_group: str) -> dict[str, object]:
    return {
        "network_id": network_id,
        "provider": "syke",
        "domain": "finland",
        "river_group": str(river_group),
        "n_catalog_stations": len(group),
        "site_ids": "|".join(sorted(group["site_id"].astype(str))),
        "latitude": float(group["latitude"].mean()),
        "longitude": float(group["longitude"].mean()),
        "prior_temperature_values_seen": False,
        "candidate_status": "metadata_candidate_pending_daily_qc",
    }


def download_stations(
    station_ids: Sequence[str],
    output_root: str | Path,
    *,
    workers: int = 20,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    selected = tuple(sorted(str(value) for value in station_ids))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        downloaded = list(executor.map(download_station, selected))
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
    "candidate_networks",
    "download_station",
    "download_stations",
    "station_catalog",
]
