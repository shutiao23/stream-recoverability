"""NLDI upstream/downstream NWIS connectivity for HUC8 candidate groups.

HUC8 membership does not imply flow connectivity. This module queries the
USGS NLDI navigation service and records a covariate; it does not drop
disconnected groups. Daily temperatures are not downloaded.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.data.http_json import get_json, with_usgs_key
from stream_recoverability.data.public_river_inventory import _as_site_id

NLDI_BASE = "https://api.water.usgs.gov/nldi/linked-data/nwissite"
NLDI_DISTANCE_KM = 200
CACHE_DIRECTIONS = ("UM", "DM")
_USGS_PREFIX = re.compile(r"^USGS[-_]?", re.IGNORECASE)


def nwis_match_key(value: Any) -> str:
    """Compare NWIS ids after dropping a USGS- prefix and leading zeros."""

    text = _as_site_id(value)
    text = _USGS_PREFIX.sub("", text)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return text.casefold()
    return digits.lstrip("0") or "0"


def normalize_nwis_site_id(value: Any) -> str:
    """Canonical NWIS site number for URLs and cache keys."""

    text = _as_site_id(value)
    text = _USGS_PREFIX.sub("", text)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return text
    if len(digits) <= 8:
        return digits.zfill(8)
    return digits


def parse_nldi_nwissite_ids(document: Mapping[str, Any] | None) -> list[str]:
    """Extract NWIS identifiers from an NLDI GeoJSON FeatureCollection."""

    if not document:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for feature in document.get("features") or []:
        if not isinstance(feature, Mapping):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
        candidates = [
            props.get("identifier"),
            props.get("id"),
            feature.get("id"),
            props.get("uri"),
        ]
        for raw in candidates:
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            text = str(raw).strip()
            if not text:
                continue
            if "monitoring-location/" in text:
                text = text.rsplit("/", 1)[-1]
            if text.lower().startswith("nwissite-"):
                text = text.split("-", 1)[-1] if text.lower().startswith("nwissite-usgs-") else text[9:]
            key = nwis_match_key(text)
            if not key or key in seen:
                continue
            if not re.search(r"\d", key):
                continue
            seen.add(key)
            found.append(normalize_nwis_site_id(text))
            break
    return found


def nldi_cache_path(cache_dir: Path, site_id: str, direction: str, distance_km: float) -> Path:
    site = normalize_nwis_site_id(site_id)
    return Path(cache_dir) / f"{site}_{str(direction).upper()}_{int(float(distance_km))}.json"


def pick_median_origin(stations: pd.DataFrame) -> pd.Series:
    """Median station by latitude, then longitude, then site_id."""

    if stations is None or stations.empty:
        raise ValueError("need at least one station to pick an NLDI origin")
    work = stations.copy()
    if "site_id" not in work.columns:
        raise ValueError("stations need a site_id column")
    work["_site"] = work["site_id"].map(_as_site_id)
    work["_lat"] = pd.to_numeric(work.get("latitude"), errors="coerce") if "latitude" in work.columns else float("nan")
    work["_lon"] = pd.to_numeric(work.get("longitude"), errors="coerce") if "longitude" in work.columns else float("nan")
    work = work.sort_values(["_lat", "_lon", "_site"], na_position="last", kind="mergesort")
    return work.iloc[len(work) // 2]


def connectivity_from_neighbor_ids(
    origin_id: str,
    group_ids: Sequence[str],
    neighbor_ids: Sequence[str],
    *,
    queried: bool,
) -> dict[str, Any]:
    """Classify UM∪DM membership. Origin is always counted as connected."""

    origin_key = nwis_match_key(origin_id)
    group = [_as_site_id(item) for item in group_ids if _as_site_id(item)]
    group_keys = [nwis_match_key(item) for item in group]
    if not queried:
        return {
            "origin_site_id": _as_site_id(origin_id),
            "flow_connected": "not_queried",
            "n_connected_stations": 1,
            "spatially_proximate_not_flow_connected": False,
            "connected_site_ids": _as_site_id(origin_id),
        }
    neighbor_keys = {nwis_match_key(item) for item in neighbor_ids}
    neighbor_keys.add(origin_key)
    connected = [site for site, key in zip(group, group_keys) if key in neighbor_keys]
    others = [key for key in group_keys if key != origin_key]
    others_hit = [key for key in others if key in neighbor_keys]
    if not others or len(others_hit) == len(others):
        status = "true"
    elif not others_hit:
        status = "false"
    else:
        status = "partial"
    return {
        "origin_site_id": _as_site_id(origin_id),
        "flow_connected": status,
        "n_connected_stations": int(len({nwis_match_key(item) for item in connected})),
        "spatially_proximate_not_flow_connected": status in {"false", "partial"},
        "connected_site_ids": ",".join(connected),
    }


def fetch_nldi_navigation(
    site_id: str,
    direction: str,
    *,
    distance_km: float = NLDI_DISTANCE_KM,
    cache_dir: Path,
    pause_s: float = 0.25,
    timeout: int = 90,
) -> dict[str, Any] | None:
    """Return a cached or live NLDI FeatureCollection. Failures are not cached."""

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = nldi_cache_path(cache_dir, site_id, direction, distance_km)
    if path.is_file():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            document = None
        else:
            if isinstance(document, dict):
                return document
    site = normalize_nwis_site_id(site_id)
    url = with_usgs_key(
        f"{NLDI_BASE}/USGS-{site}/navigation/{str(direction).upper()}/nwissite"
        f"?distance={int(float(distance_km))}"
    )
    try:
        document = get_json(url, timeout=timeout)
    except RuntimeError:
        time.sleep(max(float(pause_s), 0.0))
        return None
    if not isinstance(document, dict):
        time.sleep(max(float(pause_s), 0.0))
        return None
    path.write_text(json.dumps(document), encoding="utf-8")
    time.sleep(max(float(pause_s), 0.0))
    return document


def assess_group_flow_connectivity(
    site_ids: Sequence[str],
    stations: pd.DataFrame,
    *,
    cache_dir: Path,
    distance_km: float = NLDI_DISTANCE_KM,
    pause_s: float = 0.25,
    timeout: int = 90,
) -> dict[str, Any]:
    """Query UM and DM from the median origin. Do not drop disconnected groups."""

    wanted = [_as_site_id(item) for item in site_ids if _as_site_id(item)]
    if not wanted:
        return connectivity_from_neighbor_ids("", [], [], queried=False)
    work = stations.copy()
    work["site_id"] = work["site_id"].map(_as_site_id)
    work["_key"] = work["site_id"].map(nwis_match_key)
    wanted_keys = {nwis_match_key(item) for item in wanted}
    subset = work.loc[work["_key"].isin(wanted_keys)].drop_duplicates("_key")
    if subset.empty:
        subset = pd.DataFrame({"site_id": wanted})
    origin = pick_median_origin(subset)
    origin_id = _as_site_id(origin["site_id"])
    neighbor: list[str] = []
    queried = True
    for direction in CACHE_DIRECTIONS:
        document = fetch_nldi_navigation(
            origin_id,
            direction,
            distance_km=distance_km,
            cache_dir=cache_dir,
            pause_s=pause_s,
            timeout=timeout,
        )
        if document is None:
            queried = False
            break
        neighbor.extend(parse_nldi_nwissite_ids(document))
    result = connectivity_from_neighbor_ids(
        origin_id, wanted, neighbor, queried=queried
    )
    result["nldi_distance_km"] = int(float(distance_km))
    return result


def assess_clusters_flow_connectivity(
    clusters: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    cache_dir: Path,
    distance_km: float = NLDI_DISTANCE_KM,
    pause_s: float = 0.25,
    timeout: int = 90,
) -> pd.DataFrame:
    """Attach NLDI columns. Failed queries stay ``not_queried``; nothing is faked."""

    if clusters is None or clusters.empty:
        return clusters
    rows: list[dict[str, Any]] = []
    for index, row in clusters.iterrows():
        site_ids = [item for item in str(row.get("site_ids") or "").split(",") if item]
        payload = assess_group_flow_connectivity(
            site_ids,
            stations,
            cache_dir=cache_dir,
            distance_km=distance_km,
            pause_s=pause_s,
            timeout=timeout,
        )
        payload["network_id"] = row.get("network_id")
        rows.append(payload)
        n_done = len(rows)
        if n_done == 1 or n_done % 10 == 0:
            print(
                f"nldi {n_done}/{len(clusters)} "
                f"{payload.get('network_id')} {payload.get('flow_connected')}",
                flush=True,
            )
    extra = pd.DataFrame(rows)
    merged = clusters.merge(extra, on="network_id", how="left", suffixes=("", "_nldi"))
    return merged


__all__ = [
    "NLDI_BASE",
    "NLDI_DISTANCE_KM",
    "assess_clusters_flow_connectivity",
    "assess_group_flow_connectivity",
    "connectivity_from_neighbor_ids",
    "fetch_nldi_navigation",
    "nldi_cache_path",
    "normalize_nwis_site_id",
    "nwis_match_key",
    "parse_nldi_nwissite_ids",
    "pick_median_origin",
]
