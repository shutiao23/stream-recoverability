"""Official LUBW Cadenza daily water-temperature acquisition."""

from __future__ import annotations

import html
import http.cookiejar
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

LANDING_URL = "https://umweltdaten.lubw.baden-wuerttemberg.de/w/online-messstationen"
ORIGIN = "https://umweltdaten.lubw.baden-wuerttemberg.de"
TABLE_VIEW = "u6gf2s5q46r310DCsAlb"


def session_table(page_size: int = 50_000) -> pd.DataFrame:
    """Read the public export table while retaining its opaque state in memory."""

    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies)
    )
    headers = {"User-Agent": "stream-recoverability-lubw/1.0"}
    with opener.open(
        urllib.request.Request(LANDING_URL, headers=headers), timeout=120
    ) as response:
        page = response.read().decode("utf-8")
    match = re.search(
        r'<d-data[^>]*id="initial-workbook-state"[^>]*>(.*?)</d-data>',
        page,
        flags=re.DOTALL,
    )
    state = json.loads(html.unescape(match.group(1)).strip())["workbookNameAndHash"]
    table_url = (
        f"{ORIGIN}/workbooks/{state['id']},hash={state['hash']}"
        f"/views/{TABLE_VIEW}/tableData"
    )

    rows = []
    offset = 0
    total = 1
    while offset < total:
        url = table_url + "?" + urllib.parse.urlencode(
            {"offset": offset, "limit": page_size}
        )
        with opener.open(urllib.request.Request(url, headers=headers), timeout=240) as response:
            document = json.loads(response.read())
        total = int(document["rowsTotal"])
        for record in document["rows"]:
            values = record["values"]
            if (
                values[4] == "Temperatur"
                and values[13] == "°C"
                and values[12] is not None
            ):
                timestamp = pd.Timestamp(values[11])
                date = timestamp.tz_convert("Europe/Berlin").normalize().tz_localize(None)
                rows.append(
                    {
                        "site_id": str(values[0]),
                        "station_name": str(values[6]),
                        "river": str(values[8]).strip(),
                        "easting": float(values[1]),
                        "northing": float(values[2]),
                        "date": date,
                        "temperature_c": float(values[12]),
                        "qualifier": "A",
                        "provider_quality_status": "published_daily_mean",
                    }
                )
        offset += len(document["rows"])
    daily = pd.DataFrame(rows)
    return (
        daily.groupby(
            [
                "site_id",
                "station_name",
                "river",
                "easting",
                "northing",
                "date",
            ],
            as_index=False,
        )
        .agg(
            temperature_c=("temperature_c", "mean"),
            qualifier=("qualifier", "first"),
            provider_quality_status=("provider_quality_status", "first"),
        )
        .sort_values(["site_id", "date"])
        .reset_index(drop=True)
    )


def utm32_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Convert ETRS89 / UTM zone 32N coordinates to latitude/longitude."""

    semi_major = 6_378_137.0
    eccentricity = 0.00669438002290
    scale = 0.9996
    x = float(easting) - 500_000.0
    meridional = float(northing) / scale
    mu = meridional / (
        semi_major
        * (
            1
            - eccentricity / 4
            - 3 * eccentricity**2 / 64
            - 5 * eccentricity**3 / 256
        )
    )
    e1 = (1 - math.sqrt(1 - eccentricity)) / (
        1 + math.sqrt(1 - eccentricity)
    )
    footprint = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    second = eccentricity / (1 - eccentricity)
    c1 = second * math.cos(footprint) ** 2
    t1 = math.tan(footprint) ** 2
    n1 = semi_major / math.sqrt(1 - eccentricity * math.sin(footprint) ** 2)
    r1 = semi_major * (1 - eccentricity) / (
        1 - eccentricity * math.sin(footprint) ** 2
    ) ** 1.5
    d = x / (n1 * scale)
    latitude = footprint - (n1 * math.tan(footprint) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * second) * d**4 / 24
        + (
            61
            + 90 * t1
            + 298 * c1
            + 45 * t1**2
            - 252 * second
            - 3 * c1**2
        )
        * d**6
        / 720
    )
    longitude = math.radians(9.0) + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (
            5
            - 2 * c1
            + 28 * t1
            - 3 * c1**2
            + 8 * second
            + 24 * t1**2
        )
        * d**5
        / 120
    ) / math.cos(footprint)
    return math.degrees(latitude), math.degrees(longitude)


def station_catalog(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for site_id, group in daily.groupby("site_id", sort=True):
        latitude, longitude = utm32_to_wgs84(
            float(group["easting"].iloc[0]), float(group["northing"].iloc[0])
        )
        rows.append(
            {
                "site_id": site_id,
                "station_name": group["station_name"].iloc[0],
                "river": group["river"].iloc[0],
                "easting": float(group["easting"].iloc[0]),
                "northing": float(group["northing"].iloc[0]),
                "latitude": latitude,
                "longitude": longitude,
                "n_daily_rows": len(group),
                "start": group["date"].min(),
                "end": group["date"].max(),
            }
        )
    return pd.DataFrame(rows)


def _slug(value: str) -> str:
    translated = (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "_", translated).strip("_")


def candidate_networks(catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for river, group in catalog.groupby("river", sort=True):
        if len(group) < 3:
            continue
        rows.append(
            {
                "network_id": f"lubw_{_slug(str(river))}",
                "provider": "lubw",
                "domain": "germany",
                "river_group": str(river),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                "latitude": float(group["latitude"].mean()),
                "longitude": float(group["longitude"].mean()),
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows).sort_values("network_id").reset_index(drop=True)


def write_station_tables(
    daily: pd.DataFrame,
    candidates: pd.DataFrame,
    output_root: str | Path,
) -> None:
    selected = {
        item
        for value in candidates["site_ids"]
        for item in str(value).split("|")
    }
    output = Path(output_root)
    for site_id, group in daily.loc[daily["site_id"].isin(selected)].groupby(
        "site_id", sort=True
    ):
        directory = output / "stations" / str(site_id)
        directory.mkdir(parents=True, exist_ok=True)
        group.to_csv(directory / "daily_temperature.csv", index=False)


__all__ = [
    "candidate_networks",
    "session_table",
    "station_catalog",
    "utm32_to_wgs84",
    "write_station_tables",
]
