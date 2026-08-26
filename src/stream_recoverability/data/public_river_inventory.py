"""Look up public stream-temperature catalogs. This is a station list, not a result.

For USGS we ask only: site name, whether daily water temperature exists, and
the first and last dates in the catalog. That does not score gap recovery.
"""

from __future__ import annotations

import math
import re
import time
import urllib.parse
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import USER_AGENT, get_json

USGS_OGC = "https://api.waterdata.usgs.gov/ogcapi/v0/collections"
HUBEAU_STATION = "https://hubeau.eaufrance.fr/api/v1/temperature/station"
FOEN_LINDAS = "https://lindas.admin.ch/query"
FOEN_EXISTENZ = "https://api.existenz.ch/apiv1/hydro/locations"
DAILY_MEAN = "00003"
TEMPERATURE = "00010"
_NAME_SPLIT = re.compile(
    r"^(?P<river>.+?)\s+(?:at|near|below|above|nr\.?|bl\.?|ab\.?|@)\s+",
    re.IGNORECASE,
)


def _get_json(url: str, timeout: int = 90) -> dict[str, Any]:
    return get_json(url, timeout=timeout)


def usgs_site_name(site_id: str) -> dict[str, Any]:
    url = (
        f"{USGS_OGC}/monitoring-locations/items?"
        + urllib.parse.urlencode(
            {"f": "json", "limit": "5", "id": f"USGS-{site_id}"}
        )
    )
    document = _get_json(url)
    features = document.get("features") or []
    if not features:
        return {
            "site_id": site_id,
            "found": False,
            "name": None,
            "latitude": None,
            "longitude": None,
        }
    props = features[0].get("properties") or {}
    coords = (features[0].get("geometry") or {}).get("coordinates") or [None, None]
    return {
        "site_id": site_id,
        "found": True,
        "name": props.get("monitoring_location_name"),
        "latitude": coords[1] if len(coords) > 1 else None,
        "longitude": coords[0] if coords else None,
        "huc": props.get("hydrologic_unit_code"),
        "drainage_area_sqmi": props.get("drainage_area"),
        "site_type": props.get("site_type"),
    }


def usgs_temperature_catalog(site_id: str) -> list[dict[str, Any]]:
    url = (
        f"{USGS_OGC}/time-series-metadata/items?"
        + urllib.parse.urlencode(
            {
                "f": "json",
                "limit": "200",
                "monitoring_location_id": f"USGS-{site_id}",
                "parameter_code": TEMPERATURE,
            }
        )
    )
    document = _get_json(url)
    rows = []
    for feature in document.get("features") or []:
        props = feature.get("properties") or {}
        rows.append(
            {
                "site_id": site_id,
                "series_id": props.get("id") or feature.get("id"),
                "statistic_id": props.get("statistic_id"),
                "statistic": props.get("computation_identifier"),
                "period": props.get("computation_period_identifier"),
                "begin": props.get("begin"),
                "end": props.get("end"),
                "unit": props.get("unit_of_measure"),
            }
        )
    return rows


def pick_daily_mean(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    daily = [
        row
        for row in rows
        if str(row.get("period") or "").lower() == "daily"
        and str(row.get("statistic_id")) == DAILY_MEAN
    ]
    if not daily:
        daily = [row for row in rows if str(row.get("period") or "").lower() == "daily"]
    if not daily:
        return None
    daily = sorted(daily, key=lambda row: str(row.get("end") or ""), reverse=True)
    return daily[0]


def years_from_span(begin: str | None, end: str | None) -> float:
    if not begin or not end:
        return float("nan")
    start = pd.Timestamp(begin)
    stop = pd.Timestamp(end)
    return float((stop - start).days / 365.25)


def inventory_usgs_sites(site_ids: Sequence[str], pause_s: float = 0.15) -> pd.DataFrame:
    rows = []
    for site_id in site_ids:
        site = usgs_site_name(str(site_id))
        try:
            series = usgs_temperature_catalog(str(site_id))
        except RuntimeError as error:
            rows.append(
                {
                    **site,
                    "has_daily_temperature": False,
                    "daily_begin": None,
                    "daily_end": None,
                    "span_years": float("nan"),
                    "n_temperature_series": 0,
                    "error": str(error),
                }
            )
            time.sleep(pause_s)
            continue
        chosen = pick_daily_mean(series)
        rows.append(
            {
                **site,
                "has_daily_temperature": chosen is not None,
                "daily_begin": None if chosen is None else chosen.get("begin"),
                "daily_end": None if chosen is None else chosen.get("end"),
                "span_years": (
                    float("nan")
                    if chosen is None
                    else years_from_span(chosen.get("begin"), chosen.get("end"))
                ),
                "daily_statistic": None if chosen is None else chosen.get("statistic"),
                "n_temperature_series": len(series),
                "error": None,
            }
        )
        time.sleep(pause_s)
    return pd.DataFrame(rows)


def search_usgs_sites_by_name(name: str, limit: int = 80) -> list[dict[str, Any]]:
    url = (
        f"{USGS_OGC}/monitoring-locations/items?"
        + urllib.parse.urlencode({"f": "json", "limit": str(limit), "q": name})
    )
    document = _get_json(url, timeout=90)
    rows = []
    needle = name.lower()
    for feature in document.get("features") or []:
        props = feature.get("properties") or {}
        label = str(props.get("monitoring_location_name") or "")
        if needle not in label.lower():
            continue
        if str(props.get("site_type") or "") not in {"Stream", "ST"}:
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        rows.append(
            {
                "site_id": str(props.get("monitoring_location_number") or ""),
                "found": True,
                "name": label,
                "latitude": coords[1] if len(coords) > 1 else None,
                "longitude": coords[0] if coords else None,
                "huc": props.get("hydrologic_unit_code"),
                "drainage_area_sqmi": props.get("drainage_area"),
                "site_type": props.get("site_type"),
            }
        )
    return rows


def inventory_usgs_name_search(
    name: str, *, pause_s: float = 0.12, limit: int = 80
) -> pd.DataFrame:
    """Find stream sites whose names contain ``name`` and that have daily temperature."""

    found = search_usgs_sites_by_name(name, limit=limit)
    if not found:
        return pd.DataFrame()
    rows = []
    for site in found:
        try:
            series = usgs_temperature_catalog(str(site["site_id"]))
        except RuntimeError as error:
            rows.append({**site, "has_daily_temperature": False, "error": str(error)})
            time.sleep(pause_s)
            continue
        chosen = pick_daily_mean(series)
        rows.append(
            {
                **site,
                "has_daily_temperature": chosen is not None,
                "daily_begin": None if chosen is None else chosen.get("begin"),
                "daily_end": None if chosen is None else chosen.get("end"),
                "span_years": (
                    float("nan")
                    if chosen is None
                    else years_from_span(chosen.get("begin"), chosen.get("end"))
                ),
                "daily_statistic": None if chosen is None else chosen.get("statistic"),
                "n_temperature_series": len(series),
                "error": None,
            }
        )
        time.sleep(pause_s)
    return pd.DataFrame(rows)


def _hubeau_station_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_id": item.get("code_station"),
        "name": item.get("libelle_station"),
        "river": item.get("libelle_cours_eau"),
        "code_cours_eau": item.get("code_cours_eau"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "begin": item.get("date_debut_mesure"),
        "end": item.get("date_fin_mesure"),
        "department": item.get("libelle_departement"),
        "source": "hubeau",
    }


def inventory_hubeau_stations(size: int = 1000) -> pd.DataFrame:
    """All public Hub'Eau continuous-temperature stations, then we filter names."""

    url = HUBEAU_STATION + "?" + urllib.parse.urlencode({"size": str(size)})
    document = _get_json(url, timeout=90)
    rows = [_hubeau_station_row(item) for item in document.get("data") or []]
    return pd.DataFrame(rows)


def inventory_loire_hubeau(size: int = 1000) -> pd.DataFrame:
    """Stations whose watercourse name is the Loire itself, not similarly named streams."""

    all_stations = inventory_hubeau_stations(size=size)
    if all_stations.empty:
        return all_stations
    river = all_stations["river"].fillna("").astype(str).str.strip()
    keep = river.str.fullmatch(r"(La\s+)?Loire", case=False)
    return all_stations.loc[keep].copy()


def inventory_foen_temperature_stations() -> pd.DataFrame:
    """Swiss station names. Historical daily files are still ordered from FOEN."""

    try:
        document = _get_json(FOEN_EXISTENZ, timeout=60)
    except RuntimeError:
        document = {}
    payload = document.get("payload") if isinstance(document, dict) else None
    rows = []
    if isinstance(payload, dict):
        for code, item in payload.items():
            details = item.get("details") or {}
            rows.append(
                {
                    "site_id": details.get("id") or code,
                    "name": details.get("name") or item.get("name"),
                    "river": details.get("water-body-name"),
                    "water_body_type": details.get("water-body-type"),
                    "latitude": details.get("lat"),
                    "longitude": details.get("lon"),
                    "source": "existenz_foen_locations",
                    "historical_daily_public": False,
                }
            )
    if rows:
        return pd.DataFrame(rows)
    # LINDAS is a fallback; it often returns nothing useful for daily history.
    query = """
    PREFIX schema: <http://schema.org/>
    SELECT DISTINCT ?id ?name WHERE {
      ?station schema:identifier ?id ; schema:name ?name .
    }
    LIMIT 20
    """
    url = FOEN_LINDAS + "?" + urllib.parse.urlencode(
        {"query": query, "format": "application/sparql-results+json"}
    )
    try:
        document = _get_json(url, timeout=30)
    except RuntimeError:
        return pd.DataFrame()
    fallback = []
    for item in ((document.get("results") or {}).get("bindings") or []):
        fallback.append(
            {
                "site_id": (item.get("id") or {}).get("value"),
                "name": (item.get("name") or {}).get("value"),
                "source": "foen_lindas",
                "historical_daily_public": False,
            }
        )
    return pd.DataFrame(fallback)


def river_name_from_site_name(name: str) -> str:
    """Take the watercourse from a USGS site title such as 'Delaware River at Trenton NJ'."""

    text = " ".join(str(name or "").split())
    if not text:
        return ""
    match = _NAME_SPLIT.match(text)
    if match:
        return _clean_river_name(match.group("river"))
    lowered = text.lower()
    for token in (" River", " Creek", " Fork", " Brook", " Wash", " Canal", " Slough"):
        index = lowered.find(token.lower())
        if index > 0:
            return _clean_river_name(text[: index + len(token)])
    return _clean_river_name(text.split(",")[0])


def _clean_river_name(name: str) -> str:
    text = re.sub(r"\s+", " ", name).strip(" -")
    text = re.sub(r"^(West|East|North|South|Middle|Little|Big)\s+Fork\s+of\s+", "", text, flags=re.I)
    return text


US_STATES = (
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "Florida",
    "Georgia",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
)


def _series_rows_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for feature in document.get("features") or []:
        props = feature.get("properties") or {}
        period = str(props.get("computation_period_identifier") or "").lower()
        if period and period != "daily":
            continue
        statistic = str(props.get("statistic_id") or "")
        if statistic and statistic != DAILY_MEAN:
            continue
        site = str(props.get("monitoring_location_id") or "")
        site_id = site.removeprefix("USGS-")
        if not site_id:
            continue
        rows.append(
            {
                "site_id": site_id,
                "monitoring_location_id": site,
                "daily_begin": props.get("begin"),
                "daily_end": props.get("end"),
                "span_years": years_from_span(props.get("begin"), props.get("end")),
                "huc": props.get("hydrologic_unit_code"),
                "state_name": props.get("state_name"),
            }
        )
    return rows


def usgs_daily_mean_temperature_series(
    *,
    page_size: int = 1000,
    pause_s: float = 0.45,
    max_pages_per_state: int = 8,
    states: Sequence[str] | None = None,
) -> pd.DataFrame:
    """USGS catalog of daily mean water-temperature series, one state at a time."""

    rows: list[dict[str, Any]] = []
    for state in states or US_STATES:
        params = {
            "f": "json",
            "limit": str(page_size),
            "parameter_code": TEMPERATURE,
            "statistic_id": DAILY_MEAN,
            "state_name": state,
            "skipGeometry": "true",
            "properties": (
                "monitoring_location_id,begin,end,statistic_id,"
                "computation_period_identifier,hydrologic_unit_code,state_name"
            ),
        }
        next_url: str | None = (
            f"{USGS_OGC}/time-series-metadata/items?" + urllib.parse.urlencode(params)
        )
        pages = 0
        state_n = 0
        while next_url and pages < max_pages_per_state:
            try:
                document = _get_json(next_url, timeout=90)
            except RuntimeError as error:
                print(f"usgs catalog {state}: {error}", flush=True)
                break
            pages += 1
            chunk = _series_rows_from_document(document)
            rows.extend(chunk)
            state_n += len(chunk)
            next_url = None
            for link in document.get("links") or []:
                if link.get("rel") in {"next", "next-page"}:
                    next_url = link.get("href")
                    break
            time.sleep(pause_s)
        print(f"usgs catalog {state}: {state_n} series", flush=True)
    return pd.DataFrame(rows).drop_duplicates("site_id") if rows else pd.DataFrame()


def usgs_locations_for_ids(
    site_ids: Sequence[str], *, batch: int = 30, pause_s: float = 0.6
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    unique = [str(item) for item in dict.fromkeys(site_ids) if str(item)]
    for start in range(0, len(unique), batch):
        chunk = unique[start : start + batch]
        ids = ",".join(f"USGS-{item}" for item in chunk)
        url = (
            f"{USGS_OGC}/monitoring-locations/items?"
            + urllib.parse.urlencode(
                {
                    "f": "json",
                    "limit": str(len(chunk)),
                    "id": ids,
                    "skipGeometry": "false",
                }
            )
        )
        try:
            document = _get_json(url, timeout=90)
        except RuntimeError:
            for site_id in chunk:
                rows.append(usgs_site_name(site_id))
                time.sleep(pause_s)
            continue
        found = {}
        for feature in document.get("features") or []:
            props = feature.get("properties") or {}
            site_id = str(props.get("monitoring_location_number") or "").lstrip()
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            found[site_id] = {
                "site_id": site_id,
                "found": True,
                "name": props.get("monitoring_location_name"),
                "latitude": coords[1] if len(coords) > 1 else None,
                "longitude": coords[0] if coords else None,
                "huc": props.get("hydrologic_unit_code"),
                "drainage_area_sqmi": props.get("drainage_area"),
                "site_type": props.get("site_type"),
            }
        for site_id in chunk:
            rows.append(found.get(site_id) or {"site_id": site_id, "found": False})
        time.sleep(pause_s)
    return pd.DataFrame(rows)


def cluster_rivers_from_catalog(
    series: pd.DataFrame,
    locations: pd.DataFrame,
    *,
    min_stations: int = 4,
    min_overlap_years: float = 8.0,
    min_span_years: float = 8.0,
) -> pd.DataFrame:
    """Group long daily-temperature stream sites by watercourse name and HUC2."""

    if series.empty or locations.empty:
        return pd.DataFrame()
    merged = series.merge(locations, on="site_id", how="left", suffixes=("", "_loc"))
    merged = merged.loc[merged["span_years"].ge(min_span_years)].copy()
    site_type = merged.get("site_type", pd.Series(index=merged.index, dtype=object))
    merged = merged.loc[site_type.fillna("Stream").isin({"Stream", "ST", "Streamgage"})]
    merged["river_name"] = merged["name"].map(river_name_from_site_name)
    huc = merged["huc"].fillna(merged.get("huc_loc", "")).astype(str)
    merged["huc2"] = huc.str[:2]
    merged = merged.loc[merged["river_name"].str.len().ge(4)]
    rows = []
    for (river_name, huc2), group in merged.groupby(["river_name", "huc2"], sort=False):
        if len(group) < min_stations:
            continue
        begins = pd.to_datetime(group["daily_begin"], errors="coerce")
        ends = pd.to_datetime(group["daily_end"], errors="coerce")
        overlap_start = begins.max()
        overlap_end = ends.min()
        overlap_years = (
            float("nan")
            if pd.isna(overlap_start) or pd.isna(overlap_end)
            else max((overlap_end - overlap_start).days / 365.25, 0.0)
        )
        lat = pd.to_numeric(group.get("latitude"), errors="coerce")
        lon = pd.to_numeric(group.get("longitude"), errors="coerce")
        rows.append(
            {
                "network_id": _network_id(str(river_name), str(huc2)),
                "river_name": river_name,
                "huc2": huc2,
                "n_stations": int(len(group)),
                "site_ids": ",".join(group["site_id"].astype(str)),
                "catalog_overlap_start": None
                if pd.isna(overlap_start)
                else overlap_start.date().isoformat(),
                "catalog_overlap_end": None
                if pd.isna(overlap_end)
                else overlap_end.date().isoformat(),
                "catalog_overlap_years": overlap_years,
                "enough_overlap_years": bool(
                    pd.notna(overlap_years) and overlap_years >= min_overlap_years
                ),
                "lat_span_deg": float(lat.max() - lat.min()) if lat.notna().any() else float("nan"),
                "lon_span_deg": float(lon.max() - lon.min()) if lon.notna().any() else float("nan"),
                "states": ",".join(sorted({str(item) for item in group["state_name"].dropna()})),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["enough_overlap_years", "n_stations", "catalog_overlap_years"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _network_id(river_name: str, huc2: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", river_name.lower()).strip("_")
    return f"{slug}_huc{huc2}"


def _as_site_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    if re.fullmatch(r"-?\d+\.0", text):
        text = text[:-2]
    return text


def official_huc_digits(value: Any) -> str:
    """Digits of a USGS HUC, restoring a missing leading zero on odd lengths."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    if text.endswith(".0") and text[:-2].replace(".", "").isdigit():
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if len(digits) in {1, 3, 5, 7, 9, 11}:
        digits = digits.zfill(len(digits) + 1)
    return digits


def official_huc_prefix(value: Any, width: int) -> str:
    digits = official_huc_digits(value)
    if len(digits) < width:
        return ""
    return digits[:width]


def naive_huc_zfill_prefix(value: Any, width: int = 8) -> str:
    """Reviewer-style ``str(huc).zfill(width)[:width]``. Wrong on HUC12/floats."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.zfill(int(width))[: int(width)]


def largest_overlapping_subset(
    begins: Sequence[Any],
    ends: Sequence[Any],
    *,
    min_overlap_years: float,
) -> tuple[list[int], pd.Timestamp, pd.Timestamp, float]:
    """Largest index set whose interval intersection is at least ``T`` years.

    For each candidate start ``t`` equal to a station begin date, take stations
    with ``begin <= t`` and ``end >= t+T``. Keep the largest such set; among
    ties, keep the longest intersection, then the earliest overlap start.
    """

    start = pd.to_datetime(list(begins), errors="coerce")
    stop = pd.to_datetime(list(ends), errors="coerce")
    if len(start) == 0:
        return [], pd.NaT, pd.NaT, float("nan")
    duration = pd.Timedelta(days=float(min_overlap_years) * 365.25)
    best_idx: list[int] = []
    best_n = 0
    best_years = -1.0
    best_overlap_start = pd.NaT
    best_overlap_end = pd.NaT
    for index in range(len(start)):
        candidate = start[index]
        if pd.isna(candidate):
            continue
        horizon = candidate + duration
        keep = (start <= candidate) & (stop >= horizon) & start.notna() & stop.notna()
        count = int(keep.sum())
        if count == 0:
            continue
        overlap_start = start[keep].max()
        overlap_end = stop[keep].min()
        years = float((overlap_end - overlap_start).days / 365.25)
        if years < float(min_overlap_years):
            continue
        chosen = [int(position) for position, flag in enumerate(keep) if flag]
        better = count > best_n
        if count == best_n:
            if years > best_years + 1.0e-12:
                better = True
            elif abs(years - best_years) <= 1.0e-12:
                if pd.isna(best_overlap_start) or overlap_start < best_overlap_start:
                    better = True
                elif overlap_start == best_overlap_start and chosen < best_idx:
                    better = True
        if better:
            best_idx = chosen
            best_n = count
            best_years = years
            best_overlap_start = overlap_start
            best_overlap_end = overlap_end
    if best_n == 0:
        return [], pd.NaT, pd.NaT, float("nan")
    return best_idx, best_overlap_start, best_overlap_end, best_years


def _merge_catalog_tables(series: pd.DataFrame, locations: pd.DataFrame) -> pd.DataFrame:
    left = series.copy()
    left["site_id"] = left["site_id"].map(_as_site_id)
    if locations is None or locations.empty:
        return left
    right = locations.copy()
    right["site_id"] = right["site_id"].map(_as_site_id)
    merged = left.merge(right, on="site_id", how="left", suffixes=("", "_loc"))
    for column in ("name", "huc", "site_type", "latitude", "longitude", "state_name"):
        loc_column = f"{column}_loc"
        if column not in merged.columns and loc_column in merged.columns:
            merged[column] = merged[loc_column]
        elif column in merged.columns and loc_column in merged.columns:
            merged[column] = merged[column].where(merged[column].notna(), merged[loc_column])
    return merged


def _prepare_v2_stations(
    series: pd.DataFrame,
    locations: pd.DataFrame,
    *,
    min_span_years: float,
) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame()
    merged = _merge_catalog_tables(series, locations)
    span = pd.to_numeric(merged.get("span_years"), errors="coerce")
    merged = merged.loc[span.ge(float(min_span_years))].copy()
    if merged.empty:
        return merged
    site_type = merged.get("site_type", pd.Series(index=merged.index, dtype=object))
    merged = merged.loc[site_type.fillna("Stream").isin({"Stream", "ST", "Streamgage"})].copy()
    if merged.empty:
        return merged
    merged["river_name"] = merged.get("name", pd.Series(index=merged.index, dtype=object)).map(
        river_name_from_site_name
    )
    merged["river_key"] = merged["river_name"].map(
        lambda name: " ".join(str(name or "").split()).casefold()
    )
    huc = merged["huc"] if "huc" in merged.columns else pd.Series("", index=merged.index)
    if "huc_loc" in merged.columns:
        huc = huc.where(huc.notna() & (huc.astype(str).str.lower() != "nan"), merged["huc_loc"])
    merged["huc2"] = huc.map(lambda value: official_huc_prefix(value, 2))
    merged["huc4"] = huc.map(lambda value: official_huc_prefix(value, 4))
    merged["huc8"] = huc.map(lambda value: official_huc_prefix(value, 8))
    return merged.reset_index(drop=True)


def _v2_cluster_row(
    subset: pd.DataFrame,
    *,
    grouping: str,
    river_name: str,
    huc2: str,
    huc4: str,
    huc8: str,
    min_stations: int,
    min_overlap_years: float,
    min_span_years: float,
    n_group_long_stations: int,
    overlap_start: pd.Timestamp,
    overlap_end: pd.Timestamp,
    overlap_years: float,
) -> dict[str, Any]:
    lat = pd.to_numeric(subset.get("latitude"), errors="coerce")
    lon = pd.to_numeric(subset.get("longitude"), errors="coerce")
    states = ""
    if "state_name" in subset.columns:
        states = ",".join(sorted({str(item) for item in subset["state_name"].dropna() if str(item)}))
    if grouping == "huc8_only":
        network_id = f"huc8_{huc8}"
    elif grouping == "name_huc2":
        network_id = _network_id(str(river_name), str(huc2))
    elif grouping == "name_huc4":
        slug = re.sub(r"[^a-z0-9]+", "_", str(river_name).lower()).strip("_")
        network_id = f"{slug}_huc4_{huc4}"
    else:
        slug = re.sub(r"[^a-z0-9]+", "_", str(river_name).lower()).strip("_")
        network_id = f"{slug}_huc8_{huc8}"
    site_ids = ",".join(sorted(subset["site_id"].map(_as_site_id), key=str))
    return {
        "grouping": grouping,
        "min_stations": int(min_stations),
        "min_overlap_years": float(min_overlap_years),
        "min_span_years": float(min_span_years),
        "network_id": network_id,
        "river_name": river_name,
        "huc2": huc2,
        "huc4": huc4,
        "huc8": huc8,
        "n_stations": int(len(subset)),
        "n_group_long_stations": int(n_group_long_stations),
        "site_ids": site_ids,
        "catalog_overlap_start": None
        if pd.isna(overlap_start)
        else pd.Timestamp(overlap_start).date().isoformat(),
        "catalog_overlap_end": None
        if pd.isna(overlap_end)
        else pd.Timestamp(overlap_end).date().isoformat(),
        "catalog_overlap_years": overlap_years,
        "enough_overlap_years": bool(
            pd.notna(overlap_years) and overlap_years >= float(min_overlap_years)
        ),
        "lat_span_deg": float(lat.max() - lat.min()) if lat.notna().any() else float("nan"),
        "lon_span_deg": float(lon.max() - lon.min()) if lon.notna().any() else float("nan"),
        "states": states,
    }


def _emit_subset_clusters(
    prepared: pd.DataFrame,
    *,
    group_columns: list[str],
    grouping: str,
    min_stations: int,
    min_overlap_years: float,
    min_span_years: float,
    require_named_river: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if prepared.empty:
        return rows
    work = prepared
    if require_named_river:
        work = work.loc[work["river_key"].fillna("").astype(str).str.len().ge(4)].copy()
        if group_columns[0] == "river_name":
            group_columns = ["river_key", *group_columns[1:]]
    work = work.loc[work[group_columns[-1]].astype(str).str.len().gt(0)].copy()
    if work.empty:
        return rows
    for keys, group in work.groupby(group_columns, sort=False, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_map = dict(zip(group_columns, ("" if pd.isna(item) else str(item) for item in keys)))
        if any(not key_map.get(column) for column in group_columns):
            continue
        chosen, overlap_start, overlap_end, overlap_years = largest_overlapping_subset(
            group["daily_begin"],
            group["daily_end"],
            min_overlap_years=min_overlap_years,
        )
        if len(chosen) < int(min_stations):
            continue
        subset = group.iloc[chosen]
        names = [str(item) for item in subset["river_name"].dropna() if str(item)]
        river_name = pd.Series(names).mode().iloc[0] if names else key_map.get("river_key", "")
        if grouping == "huc8_only":
            group_names = sorted({str(item) for item in group["river_name"].dropna() if str(item)})
            river_name = group_names[0] if len(group_names) == 1 else "mixed"
        first_huc = subset["huc"].iloc[0] if "huc" in subset.columns else ""
        rows.append(
            _v2_cluster_row(
                subset,
                grouping=grouping,
                river_name=river_name,
                huc2=key_map.get("huc2") or official_huc_prefix(first_huc, 2),
                huc4=key_map.get("huc4") or official_huc_prefix(first_huc, 4),
                huc8=key_map.get("huc8") or official_huc_prefix(first_huc, 8),
                min_stations=min_stations,
                min_overlap_years=min_overlap_years,
                min_span_years=min_span_years,
                n_group_long_stations=int(len(group)),
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                overlap_years=overlap_years,
            )
        )
    return rows


def cluster_rivers_from_catalog_v2(
    series: pd.DataFrame,
    locations: pd.DataFrame,
    *,
    min_stations: int = 3,
    min_overlap_years: float = 8.0,
    min_span_years: float = 6.0,
    huc_levels: Sequence[str] | None = None,
    include_huc8_only: bool = True,
) -> pd.DataFrame:
    """Group long stream sites by name and HUC, keeping the largest T-year subset.

    Unlike :func:`cluster_rivers_from_catalog`, one short station does not kill
    the group. ``grouping=huc8_only`` ignores exact river-name match and is not
    a name-based network count. Defaults do not change the v1 function.
    """

    prepared = _prepare_v2_stations(
        series, locations, min_span_years=min_span_years
    )
    if prepared.empty:
        return pd.DataFrame()
    has_huc = (
        bool(prepared["huc2"].astype(str).str.len().gt(0).any())
        if "huc2" in prepared.columns
        else False
    )
    levels = list(huc_levels) if huc_levels is not None else (
        ["huc2", "huc4", "huc8"] if has_huc else ["huc2"]
    )
    rows: list[dict[str, Any]] = []
    for level in levels:
        if level not in {"huc2", "huc4", "huc8"}:
            raise ValueError(f"unknown huc level {level!r}")
        if level != "huc2" and not has_huc:
            continue
        rows.extend(
            _emit_subset_clusters(
                prepared,
                group_columns=["river_name", level],
                grouping=f"name_{level}",
                min_stations=min_stations,
                min_overlap_years=min_overlap_years,
                min_span_years=min_span_years,
                require_named_river=True,
            )
        )
    if include_huc8_only and has_huc and "huc8" in prepared.columns:
        rows.extend(
            _emit_subset_clusters(
                prepared,
                group_columns=["huc8"],
                grouping="huc8_only",
                min_stations=min_stations,
                min_overlap_years=min_overlap_years,
                min_span_years=min_span_years,
                require_named_river=False,
            )
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        [
            "grouping",
            "enough_overlap_years",
            "n_stations",
            "catalog_overlap_years",
            "network_id",
        ],
        ascending=[True, False, False, False, True],
    ).reset_index(drop=True)


EARTH_RADIUS_KM = 6371.0


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    *,
    radius_km: float = EARTH_RADIUS_KM,
) -> float:
    """Great-circle distance in kilometres (Earth radius 6371 km)."""

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    chord = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * float(radius_km) * math.asin(min(1.0, math.sqrt(chord)))


def _max_pairwise_km(
    latitudes: Sequence[Any],
    longitudes: Sequence[Any],
    *,
    radius_km: float = EARTH_RADIUS_KM,
) -> tuple[float, int]:
    coords = [
        (float(lat), float(lon))
        for lat, lon in zip(latitudes, longitudes)
        if pd.notna(lat) and pd.notna(lon)
    ]
    n_coords = len(coords)
    if n_coords < 2:
        return float("nan"), n_coords
    farthest = 0.0
    for i, (lat1, lon1) in enumerate(coords):
        for lat2, lon2 in coords[i + 1 :]:
            farthest = max(
                farthest,
                haversine_km(lat1, lon1, lat2, lon2, radius_km=radius_km),
            )
    return float(farthest), n_coords


def cluster_by_huc8(
    series_df: pd.DataFrame,
    locations_df: pd.DataFrame | None = None,
    min_stations: int = 3,
    min_overlap_years: float = 8,
    max_pair_km: float | None = None,
    *,
    huc_width: int = 8,
    earth_radius_km: float = EARTH_RADIUS_KM,
    huc_prefix: Callable[[Any, int], str] = official_huc_prefix,
) -> pd.DataFrame:
    """HUC8 subbasin clustering. Replaces name×HUC2 string matching.

    Returns candidate groups with exact max-overlap subset search.

    Grouping uses :func:`official_huc_prefix` at ``huc_width`` (default 8), not
    ``str(huc).zfill(8)[:8]``. The reviewer's ``zfill(8)[:8]`` is the *intent*
    for 7-digit codes such as ``3130004``; ``official_huc_prefix`` is the
    correct implementation because catalog HUCs also include values such as
    ``190101060106.0`` and ``11000020108``. Naive ``zfill(8)[:8]`` on those
    longer codes yields the wrong basin. Pass ``huc_prefix=naive_huc_zfill_prefix``
    only as a diagnostic; it is not the catalog rule.

    Long-station filter is catalog span ≥ ``min_overlap_years`` (8 years at
    the default). That matches the v2 *builder's* 8-year case, not
    :func:`cluster_rivers_from_catalog_v2`'s function default of 6 years.

    Within each HUC prefix, :func:`largest_overlapping_subset` keeps the
    largest set whose interval intersection is ≥ ``min_overlap_years``. The
    search is not truncated at 12 stations; a 13-station concurrent group
    keeps 13.

    Spatial-filter policy: when ``max_pair_km`` is set, the overlap subset is
    computed first, then that subset's maximum pairwise geodesic distance is
    measured (haversine, Earth radius 6371 km). Groups whose overlap subset
    exceeds the cap are **omitted**, not silently shrunk. Shrinking after the
    overlap search would mix a second heuristic into the grouping rule. If
    fewer than two kept stations have coordinates, the cap cannot be verified
    and the group is omitted. The returned ``max_pair_km`` is the actual
    distance of the kept set, not the cap.
    """

    if series_df is None or series_df.empty:
        return pd.DataFrame()
    width = int(huc_width)
    if width <= 0:
        raise ValueError(f"huc_width must be positive, got {huc_width!r}")
    min_stations = int(min_stations)
    min_overlap = float(min_overlap_years)
    min_span = float(min_overlap_years)
    locations = pd.DataFrame() if locations_df is None else locations_df
    prepared = _prepare_v2_stations(series_df, locations, min_span_years=min_span)
    if prepared.empty:
        return pd.DataFrame()
    huc_source = prepared["huc"] if "huc" in prepared.columns else pd.Series("", index=prepared.index)
    prepared = prepared.copy()
    prepared["_huc_key"] = huc_source.map(lambda value: huc_prefix(value, width))
    prepared = prepared.loc[prepared["_huc_key"].astype(str).str.len().eq(width)].copy()
    if prepared.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    cap = None if max_pair_km is None or (isinstance(max_pair_km, float) and pd.isna(max_pair_km)) else float(max_pair_km)
    for huc_key, group in prepared.groupby("_huc_key", sort=False, dropna=False):
        key = "" if pd.isna(huc_key) else str(huc_key)
        if len(key) != width:
            continue
        chosen, overlap_start, overlap_end, overlap_years = largest_overlapping_subset(
            group["daily_begin"],
            group["daily_end"],
            min_overlap_years=min_overlap,
        )
        if len(chosen) < min_stations:
            continue
        subset = group.iloc[chosen]
        lat = pd.to_numeric(subset.get("latitude"), errors="coerce")
        lon = pd.to_numeric(subset.get("longitude"), errors="coerce")
        actual_km, n_coords = _max_pairwise_km(lat, lon, radius_km=earth_radius_km)
        if cap is not None:
            if n_coords < 2 or pd.isna(actual_km) or float(actual_km) > cap:
                continue
        names = sorted(
            {str(item).strip() for item in subset.get("river_name", pd.Series(dtype=object)).dropna() if str(item).strip()}
        )
        site_ids = ",".join(sorted((subset["site_id"].map(_as_site_id)), key=str))
        digits = official_huc_digits(subset["huc"].iloc[0]) if "huc" in subset.columns else key
        rows.append(
            {
                "network_id": f"huc{width}_{key}",
                "grouping": f"huc{width}",
                "huc2": key[:2] if len(key) >= 2 else official_huc_prefix(digits, 2),
                "huc4": key[:4] if len(key) >= 4 else official_huc_prefix(digits, 4),
                "huc6": key[:6] if len(key) >= 6 else official_huc_prefix(digits, 6),
                "huc8": key if width == 8 else official_huc_prefix(digits, 8),
                "huc_key": key,
                "n_stations": int(len(subset)),
                "n_stations_available": int(len(group)),
                "site_ids": site_ids,
                "overlap_start": None
                if pd.isna(overlap_start)
                else pd.Timestamp(overlap_start).date().isoformat(),
                "overlap_end": None
                if pd.isna(overlap_end)
                else pd.Timestamp(overlap_end).date().isoformat(),
                "catalog_overlap_years": overlap_years,
                "enough_overlap_years": bool(
                    pd.notna(overlap_years) and overlap_years >= min_overlap
                ),
                "max_pair_km": actual_km,
                "n_stations_with_coords": int(n_coords),
                "river_names": "; ".join(names),
                "min_stations": min_stations,
                "min_overlap_years": min_overlap,
                "min_span_years": min_span,
                "distance_cap_km": cap if cap is not None else float("nan"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["n_stations", "catalog_overlap_years", "network_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def summarize_river(site_table: pd.DataFrame, *, min_span_years: float = 8.0) -> dict[str, Any]:
    usable = site_table.loc[
        site_table["has_daily_temperature"].fillna(False)
        & site_table["span_years"].ge(min_span_years)
    ]
    begins = pd.to_datetime(usable["daily_begin"], errors="coerce")
    ends = pd.to_datetime(usable["daily_end"], errors="coerce")
    overlap_start = begins.max() if not begins.empty else pd.NaT
    overlap_end = ends.min() if not ends.empty else pd.NaT
    overlap_years = (
        float("nan")
        if pd.isna(overlap_start) or pd.isna(overlap_end)
        else max((overlap_end - overlap_start).days / 365.25, 0.0)
    )
    return {
        "n_listed": int(len(site_table)),
        "n_found": int(site_table["found"].fillna(False).sum())
        if "found" in site_table
        else int(len(site_table)),
        "n_with_daily_temperature": int(site_table["has_daily_temperature"].fillna(False).sum()),
        "n_with_8yr_daily_temperature": int(len(usable)),
        "usable_site_ids": ",".join(usable["site_id"].astype(str)),
        "catalog_overlap_start": None
        if pd.isna(overlap_start)
        else overlap_start.date().isoformat(),
        "catalog_overlap_end": None
        if pd.isna(overlap_end)
        else overlap_end.date().isoformat(),
        "catalog_overlap_years": overlap_years,
        "enough_stations": int(len(usable)) >= 4,
        "enough_overlap_years": bool(overlap_years >= 8.0) if pd.notna(overlap_years) else False,
    }


__all__ = [
    "EARTH_RADIUS_KM",
    "cluster_by_huc8",
    "cluster_rivers_from_catalog",
    "cluster_rivers_from_catalog_v2",
    "haversine_km",
    "inventory_foen_temperature_stations",
    "inventory_hubeau_stations",
    "inventory_loire_hubeau",
    "inventory_usgs_name_search",
    "inventory_usgs_sites",
    "largest_overlapping_subset",
    "naive_huc_zfill_prefix",
    "official_huc_digits",
    "official_huc_prefix",
    "river_name_from_site_name",
    "summarize_river",
    "usgs_daily_mean_temperature_series",
    "usgs_locations_for_ids",
    "usgs_site_name",
    "usgs_temperature_catalog",
]
