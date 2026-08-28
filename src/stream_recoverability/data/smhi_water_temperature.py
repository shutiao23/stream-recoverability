"""Official SMHI HydroObs daily stream-temperature acquisition."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

PARAMETER_URL = (
    "https://opendata-download-hydroobs.smhi.se/"
    "api/version/latest/parameter/4.json"
)
DATA_URL = (
    "https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4/"
    "station/{site_id}/period/corrected-archive/data.csv"
)
CANDIDATE_COLUMNS = [
    "network_id",
    "provider",
    "domain",
    "river_group",
    "n_catalog_stations",
    "site_ids",
    "latitude",
    "longitude",
    "prior_temperature_values_seen",
    "candidate_status",
]


def get_bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "stream-recoverability-smhi/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def station_catalog() -> pd.DataFrame:
    document = json.loads(get_bytes(PARAMETER_URL))
    rows = []
    for station in document["station"]:
        rows.append(
            {
                "site_id": str(station["id"]),
                "station_name": station["name"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "catchment_name": station["catchmentName"],
                "catchment_number": station["catchmentNumber"],
                "provider_from": pd.to_datetime(station["from"], unit="ms"),
                "provider_to": pd.to_datetime(station["to"], unit="ms"),
                "active": station["active"],
            }
        )
    return pd.DataFrame(rows)


def parse_csv(payload: bytes, site_id: str) -> tuple[pd.DataFrame, Counter[str]]:
    lines = payload.decode("utf-8-sig").splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith("Datum")
    )
    approved = []
    counts: Counter[str] = Counter()
    for values in csv.reader(lines[start + 1 :], delimiter=";"):
        if len(values) < 3:
            continue
        quality = values[2]
        counts[quality] += 1
        if quality == "G":
            approved.append(
                {
                    "site_id": str(site_id),
                    "date": pd.to_datetime(values[0]),
                    "temperature_c": float(values[1]),
                    "provider_quality_status": quality,
                    "qualifier": "A",
                }
            )
    return (
        pd.DataFrame(
            approved,
            columns=[
                "site_id",
                "date",
                "temperature_c",
                "provider_quality_status",
                "qualifier",
            ],
        ),
        counts,
    )


def download_stations(
    catalog: pd.DataFrame,
    output_root: str | Path,
    *,
    workers: int = 12,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    station_ids = tuple(catalog["site_id"].astype(str))

    def download(site_id: str) -> tuple[pd.DataFrame, Counter[str]]:
        return parse_csv(get_bytes(DATA_URL.format(site_id=site_id)), site_id)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        downloaded = list(executor.map(download, station_ids))
    output = Path(output_root)
    frames = {}
    summaries = []
    for site_id, (daily, counts) in zip(station_ids, downloaded, strict=True):
        directory = output / "stations" / site_id
        directory.mkdir(parents=True, exist_ok=True)
        daily.to_csv(directory / "daily_temperature.csv", index=False)
        row = {
            "site_id": site_id,
            "n_g_days": counts["G"],
            "n_y_days": counts["Y"],
            "n_o_days": counts["O"],
            "n_blank_quality_days": counts[""],
        }
        pd.DataFrame([row]).to_csv(directory / "station_summary.csv", index=False)
        frames[site_id] = daily
        summaries.append(row)
    return frames, pd.DataFrame(summaries)


def _slug(value: str) -> str:
    translated = (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("å", "aa")
    )
    return re.sub(r"[^a-z0-9]+", "_", translated).strip("_")


def candidate_networks(
    catalog: pd.DataFrame,
    quality_summary: pd.DataFrame,
) -> pd.DataFrame:
    available = catalog.merge(quality_summary, on="site_id")
    available = available.loc[available["n_g_days"].gt(0)].copy()
    rows = []
    for catchment, group in available.groupby("catchment_name", sort=True):
        if not str(catchment).strip() or len(group) < 3:
            continue
        rows.append(
            {
                "network_id": f"smhi_{_slug(str(catchment))}",
                "provider": "smhi",
                "domain": "sweden",
                "river_group": str(catchment),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                "latitude": float(group["latitude"].mean()),
                "longitude": float(group["longitude"].mean()),
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)


__all__ = [
    "candidate_networks",
    "download_stations",
    "parse_csv",
    "station_catalog",
]
