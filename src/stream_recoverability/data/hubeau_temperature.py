"""Hub'Eau continuous temperature: station clustering and chronicle date spans.

Loire last-check stations are not downloaded. Empty catalog begin/end fields
are not invented; spans come from public chronique first/last points.
Hub'Eau refuses queries with page * size > 20000; chronique downloads must
be split by date windows, not by deep page numbers.
"""

from __future__ import annotations

import time
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import get_json
from stream_recoverability.data.public_river_inventory import years_from_span

HUBEAU_CHRONIQUE = "https://hubeau.eaufrance.fr/api/v1/temperature/chronique"
LOIRE_PATTERN = r"(La\s+)?Loire"
HUBEAU_MAX_WINDOW_RECORDS = 20000
HUBEAU_PAGE_SIZE = 20000
HUBEAU_CORRECT_QUALIFICATION = "1"
DAILY_CACHE_SUFFIX = "_daily_yearchunk_qc1.csv"


def _refuse_last_check_site(site_id: str) -> None:
    from stream_recoverability.data.v2_download_policy import last_check_site_ids

    if str(site_id) in last_check_site_ids():
        raise ValueError(f"last-check/Loire site {site_id} is not downloadable")


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
                "n_stations": len(group),
                "site_ids": ",".join(str(item) for item in group["site_id"]),
                "countable_public_daily": False,
                "loire_excluded": True,
                "source": "hubeau_station_names",
            }
        )
    return pd.DataFrame(rows)


def hubeau_chronicle_span(site_id: str) -> dict[str, Any]:
    """First and last public chronique timestamps. Not a full daily download."""

    _refuse_last_check_site(site_id)
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


def hubeau_spans_for_sites(
    site_ids: Sequence[str], *, pause_s: float = 0.2
) -> pd.DataFrame:
    rows = []
    for site_id in site_ids:
        try:
            rows.append(hubeau_chronicle_span(str(site_id)))
        # Catalog audit must retain arbitrary provider/transport failures.
        except Exception as error:  # noqa: BLE001
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


def hubeau_window_url(site_id: str, start: str, end: str) -> str:
    """One validated Hub'Eau window; page*size never exceeds 20,000.

    Sandre qualification 1 is ``Correcte``.  Codes 2--4 (incorrect,
    uncertain, and unqualified) are not eligible for the strict daily corpus.
    """

    params = {
        "code_station": str(site_id),
        "date_debut_mesure": str(start),
        "date_fin_mesure": str(end),
        "code_qualification": HUBEAU_CORRECT_QUALIFICATION,
        "size": str(HUBEAU_PAGE_SIZE),
        "page": "1",
        "sort": "asc",
    }
    return HUBEAU_CHRONIQUE + "?" + urllib.parse.urlencode(params)


def _rows_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in document.get("data") or []:
        rows.append(
            {
                "date": item.get("date_mesure_temp"),
                "temperature_c": item.get("resultat"),
                "quality_code": item.get("code_qualification"),
                "quality_label": item.get("libelle_qualification"),
            }
        )
    return rows


def _window_needs_split(document: dict[str, Any]) -> bool:
    data = document.get("data") or []
    count = int(document.get("count") or 0)
    has_next = bool(document.get("next") or document.get("api_next"))
    return bool(
        has_next or count > HUBEAU_MAX_WINDOW_RECORDS or len(data) >= HUBEAU_PAGE_SIZE
    )


def _fetch_window(
    site_id: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    *,
    pause_s: float,
    depth: int,
) -> list[dict[str, Any]]:
    if depth > 24:
        raise RuntimeError(f"Hub'Eau date split exceeded depth for {site_id}")
    url = hubeau_window_url(
        site_id,
        start_ts.strftime("%Y-%m-%d"),
        end_ts.strftime("%Y-%m-%d"),
    )
    document = get_json(url, timeout=90, retries=6)
    time.sleep(pause_s)
    if _window_needs_split(document) and start_ts != end_ts:
        mid = start_ts + (end_ts - start_ts) // 2
        left = _fetch_window(site_id, start_ts, mid, pause_s=pause_s, depth=depth + 1)
        right = _fetch_window(
            site_id,
            mid + pd.Timedelta(days=1),
            end_ts,
            pause_s=pause_s,
            depth=depth + 1,
        )
        return left + right
    return _rows_from_document(document)


def hubeau_chronique_rows(
    site_id: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    *,
    pause_s: float = 0.15,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Fetch chronique by calendar year, then split a year if it still exceeds 20k.

    Does not follow ``next`` page links. Only Sandre ``Correcte`` (code 1)
    observations are requested and retained. Does not invent dates: empty
    windows return no rows. Last-check/Loire site IDs are refused.
    """

    del depth
    _refuse_last_check_site(site_id)
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if pd.isna(start_ts) or pd.isna(end_ts) or end_ts < start_ts:
        return []
    rows: list[dict[str, Any]] = []
    year = int(start_ts.year)
    while year <= int(end_ts.year):
        y0 = max(start_ts, pd.Timestamp(year=year, month=1, day=1))
        y1 = min(end_ts, pd.Timestamp(year=year, month=12, day=31))
        rows.extend(_fetch_window(site_id, y0, y1, pause_s=pause_s, depth=0))
        year += 1
    return rows


def hubeau_chronique_daily(
    site_id: str,
    *,
    cache_dir: str | Path,
    max_pages: int = 80,
    page_size: int = 5000,
) -> pd.DataFrame:
    """Resample public Hub'Eau instantaneous chronique to daily mean °C.

    This is derived daily from public observations, not invented years.
    Loire last-check IDs are refused. Truncated page-walk caches named
    ``{site}_daily.csv`` are ignored.
    """

    del max_pages, page_size
    _refuse_last_check_site(site_id)
    root = Path(cache_dir)
    dest = root / "hubeau" / f"{site_id}{DAILY_CACHE_SUFFIX}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        frame = pd.read_csv(dest)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"])
            return frame
        dest.unlink()
    span = hubeau_chronicle_span(site_id)
    begin = span.get("daily_begin")
    end = span.get("daily_end")
    if not begin or not end:
        return pd.DataFrame(columns=["site_id", "date", "temperature_c"])
    rows = hubeau_chronique_rows(str(site_id), str(begin)[:10], str(end)[:10])
    raw = pd.DataFrame(rows)
    if raw.empty:
        return pd.DataFrame(columns=["site_id", "date", "temperature_c"])
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["temperature_c"] = pd.to_numeric(raw["temperature_c"], errors="coerce")
    raw = raw.loc[raw["quality_code"].astype(str).eq(HUBEAU_CORRECT_QUALIFICATION)]
    raw = raw.dropna(subset=["date", "temperature_c"])
    daily = (
        raw.set_index("date")["temperature_c"]
        .resample("D")
        .mean()
        .rename("temperature_c")
        .reset_index()
    )
    daily["site_id"] = str(site_id)
    daily["approval_status"] = "approved"
    daily["provider_quality_code"] = HUBEAU_CORRECT_QUALIFICATION
    daily = daily.dropna(subset=["temperature_c"])
    if daily.empty:
        return daily
    daily.to_csv(dest, index=False)
    return daily


__all__ = [
    "HUBEAU_CHRONIQUE",
    "HUBEAU_CORRECT_QUALIFICATION",
    "HUBEAU_MAX_WINDOW_RECORDS",
    "cluster_hubeau_rivers",
    "hubeau_chronicle_span",
    "hubeau_chronique_daily",
    "hubeau_chronique_rows",
    "hubeau_spans_for_sites",
    "hubeau_window_url",
]
