"""Bayern GKD river-temperature catalog, downloads, and candidate assembly."""

from __future__ import annotations

import csv
import html
import http.cookiejar
import io
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd

CATALOG_URL = "https://www.gkd.bayern.de/de/fluesse/wassertemperatur/tabellen"
ENQUEUE_URL = "https://www.gkd.bayern.de/de/downloadcenter/enqueue_download"
USER_AGENT = "stream-recoverability-gkd-bayern/1.0"


@dataclass(frozen=True)
class Station:
    site_id: str
    station_name: str
    river: str
    main_url: str
    download_url: str


def get_bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_catalog(document: bytes | str) -> tuple[Station, ...]:
    """Parse the official temperature table into its station inventory."""

    text = document.decode("utf-8") if isinstance(document, bytes) else document
    stations = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.DOTALL):
        match = re.search(
            r'href="(https://www\.gkd\.bayern\.de/de/fluesse/'
            r'wassertemperatur/[^\"]+?-(\d+)/messwerte\?method=tabellen)"',
            row,
        )
        if match is None:
            continue
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.DOTALL)
        clean = lambda value: html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        main_url = match.group(1).split("/messwerte", maxsplit=1)[0]
        stations.append(
            Station(
                site_id=match.group(2),
                station_name=clean(cells[0]),
                river=clean(cells[1]),
                main_url=main_url,
                download_url=f"{main_url}/download",
            )
        )
    return tuple(stations)


def download_catalog() -> tuple[Station, ...]:
    return parse_catalog(get_bytes(CATALOG_URL))


def _slug(value: str) -> str:
    translated = (
        value.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "_", translated).strip("_")


def candidate_networks(stations: Sequence[Station]) -> pd.DataFrame:
    """Group catalog stations by exact river name and retain groups of three."""

    catalog = pd.DataFrame(asdict(station) for station in stations)
    rows = []
    for river, group in catalog.groupby("river", sort=True):
        if len(group) < 3:
            continue
        rows.append(
            {
                "network_id": f"gkd_bayern_{_slug(str(river))}",
                "provider": "gkd_bayern",
                "domain": "germany",
                "river_group": str(river),
                "n_catalog_stations": len(group),
                "site_ids": "|".join(sorted(group["site_id"].astype(str))),
                "latitude": np.nan,
                "longitude": np.nan,
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows).sort_values("network_id").reset_index(drop=True)


def parse_coordinates(document: bytes | str) -> tuple[float, float]:
    text = document.decode("utf-8") if isinstance(document, bytes) else document
    match = re.search(
        r'"pinMarker":\{.*?"center_lon":"([-+0-9.]+)",'
        r'"center_lat":"([-+0-9.]+)"',
        text,
        flags=re.DOTALL,
    )
    return float(match.group(2)), float(match.group(1))


def parse_daily_csv(payload: bytes, site_id: str) -> pd.DataFrame:
    """Parse one semicolon-delimited GKD daily-mean CSV member."""

    lines = payload.decode("utf-8-sig").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("Datum;Mittelwert;Maximum;Minimum;Prüfstatus")
    )
    rows = []
    for values in csv.reader(lines[start + 1 :], delimiter=";"):
        if len(values) != 5:
            continue
        rows.append(
            {
                "site_id": str(site_id),
                "date": pd.to_datetime(values[0]),
                "temperature_c": float(values[1].replace(",", ".")),
                "maximum_c": float(values[2].replace(",", ".")),
                "minimum_c": float(values[3].replace(",", ".")),
                "provider_quality_status": values[4],
                "qualifier": "A" if values[4] == "Geprueft" else "P",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "site_id",
            "date",
            "temperature_c",
            "maximum_c",
            "minimum_c",
            "provider_quality_status",
            "qualifier",
        ],
    )


def parse_archive(payload: bytes, site_id: str) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in sorted(archive.namelist()):
            if name.lower().endswith(".csv"):
                frames.append(parse_daily_csv(archive.read(name), site_id))
    populated = [frame for frame in frames if not frame.empty]
    daily = (
        pd.concat(populated, ignore_index=True)
        if populated
        else frames[0].copy()
    )
    return (
        daily.sort_values("date", kind="mergesort")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )


def download_station(
    station: Station,
    *,
    poll_seconds: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Request and download one complete checked daily-temperature archive."""

    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies)
    )
    page_headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    with opener.open(
        urllib.request.Request(station.download_url, headers=page_headers),
        timeout=120,
    ) as response:
        response.read()
    with opener.open(
        urllib.request.Request(station.main_url, headers=page_headers), timeout=120
    ) as response:
        latitude, longitude = parse_coordinates(response.read())
    form = urllib.parse.urlencode(
        {
            "zr": "gesamt",
            "beginn": "",
            "ende": "",
            "geprueft": "1",
            "wertart": "tmw",
            "email": "",
            "t": json.dumps(
                {station.site_id: ["fluesse.wassertemperatur"]},
                separators=(",", ":"),
            ),
            "f": "",
        }
    ).encode("utf-8")
    enqueue = urllib.request.Request(
        ENQUEUE_URL,
        data=form,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": station.download_url,
        },
    )
    with opener.open(enqueue, timeout=120) as response:
        deeplink = json.loads(response.read().decode("utf-8"))["deeplink"]
    while True:
        with opener.open(
            urllib.request.Request(deeplink, headers=page_headers), timeout=120
        ) as response:
            status_page = response.read().decode("utf-8")
        if "dl=1" in status_page:
            break
        time.sleep(poll_seconds)
    with opener.open(
        urllib.request.Request(f"{deeplink}&dl=1", headers=page_headers), timeout=180
    ) as response:
        archive = response.read()
    daily = parse_archive(archive, station.site_id)
    metadata = {
        **asdict(station),
        "latitude": latitude,
        "longitude": longitude,
        "n_daily_rows": len(daily),
        "start": daily["date"].min().strftime("%Y-%m-%d") if len(daily) else None,
        "end": daily["date"].max().strftime("%Y-%m-%d") if len(daily) else None,
        "provider_quality_statuses": "|".join(
            sorted(daily["provider_quality_status"].unique())
        ),
    }
    return daily, metadata


def download_stations(
    stations: Sequence[Station],
    output_root: str | Path,
    *,
    workers: int = 6,
    downloader: Callable[[Station], tuple[pd.DataFrame, dict[str, object]]] = download_station,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Download stations concurrently and overwrite their ordinary tables."""

    with ThreadPoolExecutor(max_workers=workers) as executor:
        downloaded = list(executor.map(downloader, stations))
    output = Path(output_root)
    frames = {}
    metadata = []
    for station, (daily, details) in zip(stations, downloaded, strict=True):
        directory = output / "stations" / station.site_id
        directory.mkdir(parents=True, exist_ok=True)
        daily.to_csv(directory / "daily_temperature.csv", index=False)
        pd.DataFrame([details]).to_csv(directory / "station_summary.csv", index=False)
        frames[station.site_id] = daily
        metadata.append(details)
    return frames, pd.DataFrame(metadata)


def add_coordinates(candidates: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    result = candidates.copy()
    coordinates = metadata.set_index("site_id")[["latitude", "longitude"]]
    for index, row in result.iterrows():
        selected = coordinates.loc[str(row["site_ids"]).split("|")]
        result.loc[index, "latitude"] = float(selected["latitude"].mean())
        result.loc[index, "longitude"] = float(selected["longitude"].mean())
    return result


def merge_provider_rows(path: str | Path, additions: pd.DataFrame) -> pd.DataFrame:
    """Replace this provider's rows in a shared CSV and overwrite the table."""

    target = Path(path)
    current = pd.read_csv(target) if target.is_file() else pd.DataFrame()
    providers = set(additions["provider"].astype(str))
    if not current.empty and "provider" in current:
        current = current.loc[~current["provider"].astype(str).isin(providers)]
    result = pd.concat([current, additions], ignore_index=True, sort=False)
    result = result.sort_values(["domain", "network_id"]).reset_index(drop=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(target, index=False)
    return result


__all__ = [
    "CATALOG_URL",
    "Station",
    "add_coordinates",
    "candidate_networks",
    "download_catalog",
    "download_station",
    "download_stations",
    "merge_provider_rows",
    "parse_archive",
    "parse_catalog",
    "parse_coordinates",
    "parse_daily_csv",
]
