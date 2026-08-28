"""Reviewed daily river-temperature archive from Slovenia ARSO."""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from collections.abc import Sequence

import pandas as pd


ARCHIVE_URL = "https://vode.arso.gov.si/hidarhiv/pov_arhiv_tab.php"
NETWORKS = {
    "arso_bistrica": ("Bistrica", ("2432", "3320", "4791", "7440")),
    "arso_drava": ("Drava", ("2005", "2150", "2160")),
    "arso_dravinja": ("Dravinja", ("2600", "2620", "2640", "2652")),
    "arso_kamniska_bistrica": (
        "Kamniška Bistrica",
        ("4400", "4430", "4445"),
    ),
    "arso_kolpa": ("Kolpa", ("4820", "4828", "4860")),
    "arso_krka": ("Krka", ("7029", "7060", "7110", "7160")),
    "arso_ljubljanica": ("Ljubljanica", ("5030", "5040", "5078")),
    "arso_paka": ("Paka", ("6280", "6300", "6340")),
    "arso_sava": (
        "Sava",
        ("3420", "3465", "3530", "3570", "3660", "3725", "3850", "3900"),
    ),
    "arso_savinja": ("Savinja", ("6020", "6060", "6120", "6140", "6200")),
    "arso_soca": ("Soča", ("8031", "8060", "8080")),
    "arso_vipava": ("Vipava", ("8561", "8565", "8591", "8601")),
}
CELL_PATTERN = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.I | re.S)
ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TAG_PATTERN = re.compile(r"<[^>]+>")


def archive_url(river: str, station: str, year: int) -> str:
    return ARCHIVE_URL + "?" + urllib.parse.urlencode(
        {
            "p_vodotok": str(river),
            "p_postaja": str(station),
            "p_leto": int(year),
            "b_arhiv": "Prikaži",
        }
    )


def get_text(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "stream-recoverability/0.1 open-arso-qc"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8")


def _text(value: str) -> str:
    return html.unescape(TAG_PATTERN.sub("", value)).strip()


def parse_daily_temperature(source: str, station: str) -> pd.DataFrame:
    """Parse the official daily table's water-temperature column."""

    table_match = re.search(
        r"<table[^>]*id=[\"']lepa_tabela[\"'][^>]*>(.*?)</table>",
        source,
        re.I | re.S,
    )
    if table_match is None:
        return pd.DataFrame(
            columns=["site_id", "date", "temperature_c", "qualifier"]
        )
    table = table_match.group(1)
    rows = ROW_PATTERN.findall(table)
    headings = [_text(value).lower() for value in CELL_PATTERN.findall(rows[0])]
    temperature_columns = [
        index for index, value in enumerate(headings) if "temp. vode" in value
    ]
    if not temperature_columns:
        return pd.DataFrame(
            columns=["site_id", "date", "temperature_c", "qualifier"]
        )
    temperature_index = temperature_columns[0]
    parsed = []
    for row in rows[1:]:
        cells = [_text(value) for value in CELL_PATTERN.findall(row)]
        if len(cells) > temperature_index and cells[temperature_index]:
            parsed.append(
                {
                    "site_id": str(station),
                    "date": pd.to_datetime(cells[0], format="%d.%m.%Y"),
                    "temperature_c": float(cells[temperature_index].replace(",", ".")),
                    "qualifier": "A",
                }
            )
    return pd.DataFrame(
        parsed, columns=["site_id", "date", "temperature_c", "qualifier"]
    )


def candidate_table() -> pd.DataFrame:
    rows = []
    for network_id, (river, stations) in NETWORKS.items():
        rows.append(
            {
                "network_id": network_id,
                "provider": "arso",
                "domain": "slovenia",
                "river_group": river,
                "n_catalog_stations": len(stations),
                "site_ids": "|".join(stations),
                "latitude": float("nan"),
                "longitude": float("nan"),
                "prior_temperature_values_seen": False,
                "candidate_status": "metadata_candidate_pending_daily_qc",
            }
        )
    return pd.DataFrame(rows)


def download_station(river: str, station: str, years: Sequence[int]) -> pd.DataFrame:
    frames = [
        parse_daily_temperature(
            get_text(archive_url(river, station, int(year))), station
        )
        for year in years
    ]
    return pd.concat([frame for frame in frames if len(frame)], ignore_index=True)


__all__ = [
    "NETWORKS",
    "archive_url",
    "candidate_table",
    "download_station",
    "parse_daily_temperature",
]
