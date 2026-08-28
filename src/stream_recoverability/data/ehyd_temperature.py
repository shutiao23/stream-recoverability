"""Official Austrian eHYD surface-water temperature source inspection."""

from __future__ import annotations

import io
import json
import re
import unicodedata
import urllib.request
import zipfile
from collections.abc import Mapping
from typing import Any

import pandas as pd


STATION_URL = "https://ehyd.gv.at/services/Messstellen/json?filter=alle"
PACKAGE_URL = (
    "https://gis.lfrz.gv.at/api/ehyd/messstellen/paket/"
    "ehyd_messstellen_all_owf.zip"
)
FILE_KIND = "owf_wassertemp_monatsmittel"
MONTHLY_PATTERN = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+00:00:00;\s*([-+]?\d+(?:,\d+)?)\s*$"
)


def get_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "stream-recoverability/0.1 open-ehyd-audit"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


def surface_temperature_stations(
    feature_document: Mapping[str, Any], package_bytes: bytes
) -> pd.DataFrame:
    """Join the official feature listing to the surface-water station table."""

    available = []
    for feature in feature_document["features"]:
        properties = feature["properties"]
        for file_row in json.loads(properties.get("fjson") or "[]"):
            if file_row.get("ftyp") == FILE_KIND:
                available.append(
                    {
                        "site_id": str(properties["hzbnr01"]),
                        "file_name": str(file_row["file"]),
                        "file_number": int(file_row["filenr"]),
                        "metadata_start_year": int(file_row["filefrom"]),
                        "metadata_end_year": int(file_row["fileto"]),
                        "temporal_resolution": "monthly_mean",
                    }
                )
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        station_bytes = archive.read("messstellen_owf.csv")
    stations = pd.read_csv(
        io.BytesIO(station_bytes),
        sep=";",
        encoding="cp1252",
        dtype={"hzbnr01": str},
    )
    stations = stations.rename(
        columns={
            "hzbnr01": "site_id",
            "mstnam02": "station_name",
            "gew03": "river_name",
            "egarea05": "catchment_area_km2",
        }
    )
    return pd.DataFrame(available).merge(
        stations[
            ["site_id", "station_name", "river_name", "catchment_area_km2"]
        ],
        on="site_id",
    )


def exact_river_candidates(stations: pd.DataFrame) -> pd.DataFrame:
    """Exact official river-name groups with 3+ stations and 8+ common years."""

    rows = []
    for river, group in stations.groupby("river_name", sort=False):
        common_start = int(group["metadata_start_year"].max())
        common_end = int(group["metadata_end_year"].min())
        if len(group) >= 3 and common_end - common_start >= 8:
            rows.append(
                {
                    "network_id": f"ehyd_{_slug(str(river))}",
                    "provider": "ehyd",
                    "domain": "austria",
                    "river_group": str(river),
                    "n_catalog_stations": len(group),
                    "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                    "latitude": float("nan"),
                    "longitude": float("nan"),
                    "prior_temperature_values_seen": False,
                    "candidate_status": "source_qc_failed_monthly_only",
                    "metadata_common_start_year": common_start,
                    "metadata_common_end_year": common_end,
                    "temporal_resolution": "monthly_mean",
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["n_catalog_stations", "network_id"], ascending=[False, True]
    )


def parse_monthly_temperature(payload: bytes, site_id: str) -> pd.DataFrame:
    """Parse one official semicolon-delimited WT monthly-mean file."""

    rows = []
    for line in payload.decode("cp1252").splitlines():
        match = MONTHLY_PATTERN.fullmatch(line.strip())
        if match is not None:
            rows.append(
                {
                    "site_id": str(site_id),
                    "date": pd.to_datetime(match.group(1), format="%d.%m.%Y"),
                    "temperature_c": float(match.group(2).replace(",", ".")),
                }
            )
    return pd.DataFrame(rows, columns=["site_id", "date", "temperature_c"])


def monthly_network(
    package_bytes: bytes, stations: pd.DataFrame, station_ids: tuple[str, ...]
) -> pd.DataFrame:
    """Read selected official monthly files directly from the downloaded package."""

    lookup = stations.set_index("site_id")
    frames = []
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        for station in station_ids:
            file_name = str(lookup.loc[station, "file_name"])
            frames.append(
                parse_monthly_temperature(
                    archive.read(f"WT-Monatsmittel/{file_name}"), station
                )
            )
    return pd.concat([frame for frame in frames if len(frame)], ignore_index=True)


__all__ = [
    "FILE_KIND",
    "PACKAGE_URL",
    "STATION_URL",
    "exact_river_candidates",
    "get_bytes",
    "monthly_network",
    "parse_monthly_temperature",
    "surface_temperature_stations",
]
