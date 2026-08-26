"""Hub'Eau continuous temperature: station clustering and chronicle date spans.

Loire last-check stations are not downloaded. Empty catalog begin/end fields
are not invented; spans come from public chronique first/last points.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Sequence
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import get_json
from stream_recoverability.data.public_river_inventory import years_from_span

HUBEAU_CHRONIQUE = "https://hubeau.eaufrance.fr/api/v1/temperature/chronique"
LOIRE_PATTERN = r"(La\s+)?Loire"


def cluster_hubeau_rivers(
    stations: pd.DataFrame,
    *,
    min_stations: int = 3,
    exclude_loire: bool = True,
) -> pd.DataFrame:
    """Name clusters from the public station table. Not a daily-year inventory."""

    if stations.empty or "river" not in stations.columns:
        return pd.DataFrame()
    frame = stations.copy()
    frame["river"] = frame["river"].fillna("").astype(str).str.strip()
    frame = frame.loc[frame["river"].ne("")]
    if exclude_loire:
        loire = frame["river"].str.fullmatch(LOIRE_PATTERN, case=False)
        frame = frame.loc[~loire.fillna(False)]
    rows = []
    for river, group in frame.groupby("river", sort=False):
        if len(group) < int(min_stations):
            continue
        rows.append(
            {
                "river": river,
                "n_stations": int(len(group)),
                "site_ids": ",".join(str(item) for item in group["site_id"]),
                "countable_public_daily": False,
                "loire_excluded": True,
                "source": "hubeau_station_names",
            }
        )
    return pd.DataFrame(rows)


def hubeau_chronicle_span(site_id: str) -> dict[str, Any]:
    """First and last public chronique timestamps. Not a full daily download."""

    base = {"code_station": str(site_id), "size": "1"}
    first = get_json(
        HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode({**base, "sort": "asc"}),
        timeout=45,
        retries=3,
    )
    last = get_json(
        HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode({**base, "sort": "desc"}),
        timeout=45,
        retries=3,
    )
    first_row = (first.get("data") or [{}])[0] if first.get("data") else {}
    last_row = (last.get("data") or [{}])[0] if last.get("data") else {}
    begin = (
        first_row.get("date_mesure_temp")
        or first_row.get("date_debut_mesure")
        or first_row.get("date_obs")
    )
    end = (
        last_row.get("date_mesure_temp")
        or last_row.get("date_fin_mesure")
        or last_row.get("date_obs")
    )
    count = first.get("count")
    return {
        "site_id": str(site_id),
        "daily_begin": begin,
        "daily_end": end,
        "span_years": years_from_span(begin, end) if begin and end else float("nan"),
        "n_points_reported": count,
        "temporal_resolution": "instantaneous_not_daily",
        "countable_public_daily": False,
        "loire_last_check": False,
        "source": "hubeau_chronique_span",
    }


def hubeau_spans_for_sites(site_ids: Sequence[str], *, pause_s: float = 0.2) -> pd.DataFrame:
    import time

    rows = []
    for site_id in site_ids:
        try:
            rows.append(hubeau_chronicle_span(str(site_id)))
        except Exception as error:
            rows.append(
                {
                    "site_id": str(site_id),
                    "daily_begin": None,
                    "daily_end": None,
                    "span_years": float("nan"),
                    "error": str(error),
                    "source": "hubeau_chronique_span",
                }
            )
        time.sleep(pause_s)
    return pd.DataFrame(rows)


def hubeau_chronique_daily(
    site_id: str,
    *,
    cache_dir: str | Path,
    max_pages: int = 80,
    page_size: int = 5000,
) -> pd.DataFrame:
    """Resample public Hub'Eau instantaneous chronique to daily mean °C.

    This is derived daily from public observations, not invented years.
    Loire last-check IDs must not be passed in.
    """

    import time
    from pathlib import Path as _Path

    root = _Path(cache_dir)
    dest = root / "hubeau" / f"{site_id}_daily.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        frame = pd.read_csv(dest)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"])
            return frame
    rows: list[dict[str, Any]] = []
    params = {
        "code_station": str(site_id),
        "size": str(int(page_size)),
        "sort": "asc",
    }
    url: str | None = HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode(params)
    pages = 0
    while url and pages < int(max_pages):
        document = get_json(url, timeout=90, retries=4)
        pages += 1
        for item in document.get("data") or []:
            rows.append(
                {
                    "date": item.get("date_mesure_temp"),
                    "temperature_c": item.get("resultat"),
                }
            )
        next_url = document.get("next") or document.get("api_next")
        if not next_url:
            for link in document.get("links") or []:
                if str(link.get("rel") or "") in {"next", "next-page"}:
                    next_url = link.get("href")
                    break
        count = int(document.get("count") or 0)
        if next_url:
            url = str(next_url)
        elif pages * int(page_size) < count:
            paged = dict(params)
            paged["page"] = str(pages + 1)
            url = HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode(paged)
        else:
            url = None
        time.sleep(0.15)
    raw = pd.DataFrame(rows)
    if raw.empty:
        empty = pd.DataFrame(columns=["site_id", "date", "temperature_c"])
        empty.to_csv(dest, index=False)
        return empty
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["temperature_c"] = pd.to_numeric(raw["temperature_c"], errors="coerce")
    raw = raw.dropna(subset=["date", "temperature_c"])
    daily = (
        raw.set_index("date")["temperature_c"]
        .resample("D")
        .mean()
        .rename("temperature_c")
        .reset_index()
    )
    daily["site_id"] = str(site_id)
    daily = daily.dropna(subset=["temperature_c"])
    daily.to_csv(dest, index=False)
    return daily


__all__ = [
    "HUBEAU_CHRONIQUE",
    "cluster_hubeau_rivers",
    "hubeau_chronicle_span",
    "hubeau_chronique_daily",
    "hubeau_spans_for_sites",
]
