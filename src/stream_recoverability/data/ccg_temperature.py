"""Canadian Coast Guard St. Lawrence daily temperature source audit."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

PAGE = (
    "https://navigation-electronique.canada.ca/topics/"
    "water-levels/central/temperatures-en"
)
LOCATIONS = {
    "mtl_b": ("Montréal", 45.5766, -73.5021),
    "sor": ("Sorel", 46.0627, -73.0504),
    "tr": ("Trois-Rivières", 46.3292, -72.5382),
    "qc": ("Québec", 46.7867, -71.2243),
}


def parse_embedded_daily(html: str, location: str) -> pd.DataFrame:
    match = re.search(r"let data = (\[.*?\]);", html, re.DOTALL)
    if match is None:
        raise ValueError("embedded Coast Guard temperature data not found")
    rows = []
    for item in json.loads(match.group(1)):
        if item.get("t") is None:
            continue
        rows.append(
            {
                "site_id": str(location),
                "date": pd.to_datetime(item["date"]),
                "temperature_c": float(item["t"]),
                # The provider explicitly labels these observations as not
                # validated or checked. Preserve that status for fail-closed QC.
                "qualifier": "P",
                "provider_quality_status": "not_validated_or_checked",
            }
        )
    return pd.DataFrame(rows)


def download_year(location: str, year: int) -> pd.DataFrame:
    url = PAGE + "?" + urllib.parse.urlencode(
        {"type": "historical", "location": location, "year": int(year)}
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "stream-recoverability/1.1 canada-source-audit"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return parse_embedded_daily(response.read().decode("utf-8"), location)


def download_archive(
    *, years: range = range(2005, 2026), workers: int = 8
) -> pd.DataFrame:
    tasks = [(location, year) for location in LOCATIONS for year in years]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        frames = list(executor.map(lambda item: download_year(*item), tasks))
    return pd.concat(frames, ignore_index=True).drop_duplicates(["site_id", "date"])


def candidate() -> dict[str, object]:
    return {
        "network_id": "ccg_st_lawrence_ship_channel",
        "provider": "canadian_coast_guard",
        "domain": "canada",
        "river_group": "St. Lawrence ship channel",
        "n_catalog_stations": len(LOCATIONS),
        "site_ids": "|".join(LOCATIONS),
        "latitude": sum(item[1] for item in LOCATIONS.values()) / len(LOCATIONS),
        "longitude": sum(item[2] for item in LOCATIONS.values()) / len(LOCATIONS),
        "prior_temperature_values_seen": False,
        "candidate_status": "source_quality_audit",
    }


__all__ = ["LOCATIONS", "candidate", "download_archive", "parse_embedded_daily"]
