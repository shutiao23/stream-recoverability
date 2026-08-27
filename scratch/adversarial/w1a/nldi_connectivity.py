"""NLDI UM+DM connectivity for HUC8 candidate groups (W1-A competing client).

HUC8 is a reporting-unit cut, not a flow network. Two creeks in one subbasin
can share a HUC8 and never meet. This module queries USGS NLDI navigation and
**does not drop** disconnected groups: they stay as
``spatially_proximate_not_flow_connected``.

Live NLDI of all catalog groups is owned by Implementer A. This client is
fixture-tested and may optionally query a handful of groups. Do not hammer
the API.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pandas as pd

GetJson = Callable[..., dict[str, Any]]

NLDI_BASE = "https://api.water.usgs.gov/nldi/linked-data/nwissite"
NLDI_DISTANCE_KM = 200
_USGS_PREFIX = re.compile(r"^USGS-?", re.IGNORECASE)
_NON_DIGITS = re.compile(r"\D")


def as_site_id(value: Any) -> str:
    """Canonical catalog site id: strip USGS- and float ``.0``, keep significant zeros."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    text = _USGS_PREFIX.sub("", text)
    if re.fullmatch(r"-?\d+\.0", text):
        text = text[:-2]
    return text


def nldi_match_keys(value: Any) -> set[str]:
    """IDs that might appear in an NLDI FeatureCollection for one NWIS site.

    NLDI returns ``USGS-01608500``, ``01608500``, or a bare int. Leading zeros
    are significant for 8-digit NWIS numbers and must not be stripped from
    15-digit groundwater/special ids. Matching uses several equivalent keys.
    """

    raw = as_site_id(value)
    if not raw:
        return set()
    keys = {raw, raw.lower(), f"USGS-{raw}", f"USGS-{raw}".lower()}
    if raw.isdigit():
        keys.add(str(int(raw)))
        if len(raw) < 8:
            padded = raw.zfill(8)
            keys.update({padded, f"USGS-{padded}"})
        if len(raw) == 8:
            stripped = raw.lstrip("0") or "0"
            keys.update({stripped, f"USGS-{stripped}"})
    return keys


def normalize_nwis_id(value: Any) -> str:
    """Single display/cache key: USGS- stripped, float tails removed."""

    return as_site_id(value)


def nldi_navigation_url(
    site_id: str, direction: str, *, distance_km: int = NLDI_DISTANCE_KM
) -> str:
    direction = str(direction).strip().upper()
    if direction not in {"UM", "DM"}:
        raise ValueError(f"direction must be UM or DM, got {direction!r}")
    site = as_site_id(site_id)
    if not site:
        raise ValueError("empty site_id")
    return (
        f"{NLDI_BASE}/USGS-{site}/navigation/{direction}/nwissite"
        f"?distance={int(distance_km)}"
    )


def _feature_id_candidates(feature: Mapping[str, Any]) -> list[Any]:
    props = feature.get("properties") if isinstance(feature, Mapping) else None
    props = props if isinstance(props, Mapping) else {}
    return [
        feature.get("id") if isinstance(feature, Mapping) else None,
        props.get("identifier"),
        props.get("id"),
        props.get("monitoring_location_number"),
        props.get("site_no"),
        props.get("sourceName"),
    ]


def parse_nldi_feature_collection(document: Any) -> set[str]:
    """Parse NLDI JSON into catalog site ids.

    Empty FeatureCollections, missing ``features``, and non-dict payloads
    yield an empty set (isolated / no neighbors), not an exception.
    """

    if document is None:
        return set()
    if isinstance(document, (bytes, str)):
        try:
            document = json.loads(document)
        except json.JSONDecodeError:
            return set()
    if not isinstance(document, Mapping):
        return set()
    features = document.get("features")
    if features is None:
        return set()
    if not isinstance(features, Sequence) or isinstance(features, (str, bytes)):
        return set()
    found: set[str] = set()
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        for candidate in _feature_id_candidates(feature):
            site = as_site_id(candidate)
            if site:
                found.add(site)
                break
    return found


def cache_path(
    cache_dir: str | Path, site_id: str, direction: str, distance_km: int
) -> Path:
    site = as_site_id(site_id) or "unknown"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", site)
    return Path(cache_dir) / f"{safe}_{direction.upper()}_{int(distance_km)}.json"


def _is_http_status(error: BaseException, code: int) -> bool:
    text = str(error)
    if f"HTTP {code}" in text:
        return True
    if isinstance(error, urllib.error.HTTPError) and int(error.code) == int(code):
        return True
    return False


def load_cached_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_cached_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def query_nldi_direction(
    site_id: str,
    direction: str,
    *,
    cache_dir: str | Path,
    distance_km: int = NLDI_DISTANCE_KM,
    get_json: GetJson | None = None,
    pause_s: float = 0.25,
) -> tuple[set[str], str]:
    """Return (site ids in that navigation, status).

    Status:
      ``ok`` — 200 JSON parsed (possibly empty features)
      ``isolated_404`` — HTTP 404, treated as no neighbors (not a dropped group)
      ``rate_limited`` — HTTP 429 survived retries / still failing
      ``error`` — other transport failure
    """

    path = cache_path(cache_dir, site_id, direction, distance_km)
    cached = load_cached_json(path)
    if cached is not None:
        meta_status = str(cached.get("_w1a_status") or "ok")
        if meta_status == "isolated_404":
            return set(), "isolated_404"
        return parse_nldi_feature_collection(cached), "ok"

    if get_json is None:
        from stream_recoverability.data.http_json import get_json as get_json

    url = nldi_navigation_url(site_id, direction, distance_km=distance_km)
    try:
        document = get_json(url, timeout=60)
    except Exception as error:  # noqa: BLE001 — must classify 404 vs 429 vs other
        if _is_http_status(error, 404):
            write_cached_json(
                path,
                {
                    "type": "FeatureCollection",
                    "features": [],
                    "_w1a_status": "isolated_404",
                    "_w1a_url": url,
                },
            )
            return set(), "isolated_404"
        if _is_http_status(error, 429):
            return set(), "rate_limited"
        return set(), "error"
    if not isinstance(document, dict):
        document = {"type": "FeatureCollection", "features": [], "_w1a_status": "ok"}
    write_cached_json(path, document)
    if pause_s:
        time.sleep(float(pause_s))
    return parse_nldi_feature_collection(document), "ok"


def pick_median_station(
    latitudes: Sequence[Any],
    longitudes: Sequence[Any],
    site_ids: Sequence[Any],
) -> str:
    """Median station by lat, then lon, then site_id. Origin of UM+DM queries."""

    rows = []
    for lat, lon, site in zip(latitudes, longitudes, site_ids):
        site_id = as_site_id(site)
        if not site_id:
            continue
        lat_n = pd.to_numeric(lat, errors="coerce")
        lon_n = pd.to_numeric(lon, errors="coerce")
        rows.append((lat_n, lon_n, site_id))
    if not rows:
        fallback = [as_site_id(item) for item in site_ids if as_site_id(item)]
        return fallback[len(fallback) // 2] if fallback else ""
    rows.sort(
        key=lambda item: (
            pd.isna(item[0]),
            float(item[0]) if pd.notna(item[0]) else 0.0,
            pd.isna(item[1]),
            float(item[1]) if pd.notna(item[1]) else 0.0,
            item[2],
        )
    )
    return rows[len(rows) // 2][2]


def _group_connected(
    origin: str,
    neighbors: set[str],
    group_sites: Sequence[str],
) -> tuple[str, int, list[str]]:
    origin_keys = nldi_match_keys(origin)
    neighbor_keys: set[str] = set()
    for item in neighbors:
        neighbor_keys.update(nldi_match_keys(item))
    neighbor_keys.update(origin_keys)

    connected: list[str] = []
    for site in group_sites:
        keys = nldi_match_keys(site)
        if keys & neighbor_keys:
            connected.append(site)
    if origin not in connected and as_site_id(origin):
        connected.append(as_site_id(origin))
    n_connected = len(set(connected))
    n_group = len({as_site_id(item) for item in group_sites if as_site_id(item)})
    others = n_group - 1
    others_connected = n_connected - 1
    if others <= 0:
        status = "true"
    elif others_connected <= 0:
        status = "false"
    elif others_connected < others:
        status = "partial"
    else:
        status = "true"
    return status, n_connected, sorted(set(connected))


def annotate_group_connectivity(
    site_ids: Sequence[str],
    latitudes: Sequence[Any],
    longitudes: Sequence[Any],
    *,
    cache_dir: str | Path,
    get_json: GetJson | None = None,
    distance_km: int = NLDI_DISTANCE_KM,
    pause_s: float = 0.25,
    query: bool = True,
) -> dict[str, Any]:
    """UM∪DM connectivity. Never deletes the group.

    ``spatially_proximate_not_flow_connected`` is True only when the query
    succeeded and connectivity is ``false`` or ``partial``. ``not_queried``
    does not pretend the group is disconnected.
    """

    sites = [as_site_id(item) for item in site_ids if as_site_id(item)]
    origin = pick_median_station(latitudes, longitudes, site_ids)
    empty = {
        "nldi_origin_site_id": origin,
        "flow_connected": "not_queried",
        "n_connected_stations": 1 if origin else 0,
        "connected_site_ids": origin,
        "spatially_proximate_not_flow_connected": False,
        "nldi_um_status": "not_queried",
        "nldi_dm_status": "not_queried",
    }
    if not query or not origin:
        return empty

    um_ids, um_status = query_nldi_direction(
        origin,
        "UM",
        cache_dir=cache_dir,
        distance_km=distance_km,
        get_json=get_json,
        pause_s=pause_s,
    )
    dm_ids, dm_status = query_nldi_direction(
        origin,
        "DM",
        cache_dir=cache_dir,
        distance_km=distance_km,
        get_json=get_json,
        pause_s=pause_s,
    )
    transport_fail = {um_status, dm_status} <= {"error", "rate_limited", "not_queried"}
    both_failed = um_status in {"error", "rate_limited"} and dm_status in {
        "error",
        "rate_limited",
    }
    if both_failed or (transport_fail and not um_ids and not dm_ids and um_status != "isolated_404"):
        if um_status == "isolated_404" or dm_status == "isolated_404":
            pass
        else:
            out = dict(empty)
            out["nldi_um_status"] = um_status
            out["nldi_dm_status"] = dm_status
            out["flow_connected"] = "not_queried"
            return out

    neighbors = set(um_ids) | set(dm_ids)
    status, n_connected, connected = _group_connected(origin, neighbors, sites)
    proximate = status in {"false", "partial"}
    return {
        "nldi_origin_site_id": origin,
        "flow_connected": status,
        "n_connected_stations": int(n_connected),
        "connected_site_ids": ",".join(connected),
        "spatially_proximate_not_flow_connected": bool(proximate),
        "nldi_um_status": um_status,
        "nldi_dm_status": dm_status,
    }


def annotate_clusters(
    clusters: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    cache_dir: str | Path,
    get_json: GetJson | None = None,
    query: bool = False,
    max_groups: int | None = None,
    pause_s: float = 0.25,
) -> pd.DataFrame:
    """Attach NLDI columns. Groups are never filtered out here."""

    frame = clusters.copy()
    for column, default in (
        ("nldi_origin_site_id", ""),
        ("flow_connected", "not_queried"),
        ("n_connected_stations", pd.NA),
        ("connected_site_ids", ""),
        ("spatially_proximate_not_flow_connected", False),
        ("nldi_um_status", "not_queried"),
        ("nldi_dm_status", "not_queried"),
    ):
        if column not in frame.columns:
            frame[column] = default
    if frame.empty:
        return frame
    station_lookup = {}
    if stations is not None and not stations.empty:
        work = stations.copy()
        work["site_id"] = work["site_id"].map(as_site_id)
        station_lookup = {
            row.site_id: row for row in work.itertuples(index=False) if row.site_id
        }
    n_done = 0
    for index, row in frame.iterrows():
        if max_groups is not None and n_done >= int(max_groups):
            break
        sites = [as_site_id(item) for item in str(row.get("site_ids") or "").split(",") if as_site_id(item)]
        lats = []
        lons = []
        for site in sites:
            rec = station_lookup.get(site)
            lats.append(getattr(rec, "latitude", None) if rec is not None else None)
            lons.append(getattr(rec, "longitude", None) if rec is not None else None)
        payload = annotate_group_connectivity(
            sites,
            lats,
            lons,
            cache_dir=cache_dir,
            get_json=get_json,
            pause_s=pause_s,
            query=query,
        )
        for key, value in payload.items():
            frame.at[index, key] = value
        n_done += 1
    return frame


__all__ = [
    "NLDI_BASE",
    "NLDI_DISTANCE_KM",
    "annotate_clusters",
    "annotate_group_connectivity",
    "as_site_id",
    "nldi_match_keys",
    "nldi_navigation_url",
    "normalize_nwis_id",
    "parse_nldi_feature_collection",
    "pick_median_station",
    "query_nldi_direction",
]
