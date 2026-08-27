"""UK EA spatial (lat/lon) clustering for W6 Europe.

River names are not required. dateOpened is not a daily-year span. A catalog
cluster is not T8. T8 / complete_enough needs 3 stations, ≥8 overlapping
daily years, and ≥5*365 days with min 3 concurrent stations.

Spatial-filter policy matches HUC8: measure max pairwise geodesic distance
(haversine, Earth radius 6371 km) on the overlap subset after daily download,
then omit groups that exceed the declared cap. Groups are not silently shrunk.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from stream_recoverability.data.hubeau_temperature import HUBEAU_SANDRE_CORRECTE_NOTE
from stream_recoverability.data.public_river_inventory import (
    EARTH_RADIUS_KM,
    haversine_km,
)
from stream_recoverability.data.public_temperature import overlap_report

DEFAULT_CAP_KM = 50.0
SENSITIVITY_CAP_KM = 100.0
MIN_STATIONS = 3
MIN_OVERLAP_YEARS = 8.0
MIN_CONCURRENT_DAYS = 5 * 365
DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER = 8
# Hydrology API GUIDs contain a hyphen. EA event / bathing / logger codes do not.
EVENT_MONITOR_SITE_ID = re.compile(r"^(E\d|EN\d|EP\d|GPRS|P\d|GSML)", re.IGNORECASE)

CLUSTER_COLUMNS = [
    "cluster_id",
    "n_stations",
    "max_pairwise_km",
    "site_ids",
    "cap_km",
    "countable_public_daily",
]


def is_hydrometric_site_id(site_id: str) -> bool:
    """True for hydrology GUIDs and named hydrometric IDs, not event monitors."""

    token = str(site_id).strip()
    if not token:
        return False
    if "-" in token:
        return True
    return EVENT_MONITOR_SITE_ID.match(token) is None


def hydrometric_stations(stations: pd.DataFrame) -> pd.DataFrame:
    """Drop event-monitor IDs before spatial clustering for T8 downloads."""

    if stations is None or stations.empty or "site_id" not in stations.columns:
        return pd.DataFrame() if stations is None else stations.iloc[0:0].copy()
    mask = stations["site_id"].map(lambda value: is_hydrometric_site_id(str(value)))
    return stations.loc[mask].copy()


def pairwise_geodesic_km(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    *,
    radius_km: float = EARTH_RADIUS_KM,
) -> np.ndarray:
    """NxN geodesic distance matrix (km). Diagonal is 0."""

    lat = np.radians(np.asarray(latitudes, dtype=float))
    lon = np.radians(np.asarray(longitudes, dtype=float))
    dphi = lat[:, None] - lat[None, :]
    dlambda = lon[:, None] - lon[None, :]
    chord = (
        np.sin(dphi / 2.0) ** 2
        + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlambda / 2.0) ** 2
    )
    dist = 2.0 * float(radius_km) * np.arcsin(np.minimum(1.0, np.sqrt(chord)))
    np.fill_diagonal(dist, 0.0)
    return dist


def max_pairwise_km(
    latitudes: pd.Series | list[Any],
    longitudes: pd.Series | list[Any],
    *,
    radius_km: float = EARTH_RADIUS_KM,
) -> float:
    coords = [
        (float(lat), float(lon))
        for lat, lon in zip(latitudes, longitudes, strict=False)
        if pd.notna(lat) and pd.notna(lon)
    ]
    if len(coords) < 2:
        return float("nan")
    farthest = 0.0
    for i, (lat1, lon1) in enumerate(coords):
        for lat2, lon2 in coords[i + 1 :]:
            farthest = max(farthest, haversine_km(lat1, lon1, lat2, lon2, radius_km=radius_km))
    return float(farthest)


def cluster_uk_ea_spatial(
    stations: pd.DataFrame,
    *,
    cap_km: float = DEFAULT_CAP_KM,
    min_stations: int = MIN_STATIONS,
) -> pd.DataFrame:
    """Complete-linkage groups with max pairwise geodesic km ≤ cap.

    Does not require riverName. Does not use dateOpened. Catalog output is
    never countable_public_daily.
    """

    empty = pd.DataFrame(columns=CLUSTER_COLUMNS)
    if stations is None or stations.empty:
        return empty
    if "site_id" not in stations.columns:
        raise ValueError("stations must include site_id")
    if "latitude" not in stations.columns or "longitude" not in stations.columns:
        raise ValueError("stations must include latitude and longitude")
    frame = stations.copy()
    frame["site_id"] = frame["site_id"].map(lambda value: str(value).strip())
    frame = frame.loc[frame["site_id"].ne("")].drop_duplicates("site_id")
    frame["_lat"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["_lon"] = pd.to_numeric(frame["longitude"], errors="coerce")
    located = frame.loc[frame["_lat"].notna() & frame["_lon"].notna()].reset_index(drop=True)
    if len(located) < int(min_stations):
        return empty
    cap = float(cap_km)
    dist = pairwise_geodesic_km(located["_lat"].to_numpy(), located["_lon"].to_numpy())
    dist = 0.5 * (dist + dist.T)
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)
    if condensed.size == 0:
        return empty
    labels = fcluster(linkage(condensed, method="complete"), t=cap, criterion="distance")
    located["_cluster"] = labels
    rows: list[dict[str, Any]] = []
    for _, group in located.groupby("_cluster", sort=False):
        idx = group.index.to_numpy()
        actual_km = float(dist[np.ix_(idx, idx)].max()) if len(idx) > 1 else 0.0
        if len(group) < int(min_stations):
            continue
        if pd.isna(actual_km) or actual_km > cap:
            continue
        site_ids = ",".join(sorted(str(item) for item in group["site_id"]))
        rows.append(
            {
                "n_stations": int(len(group)),
                "max_pairwise_km": actual_km,
                "site_ids": site_ids,
                "cap_km": cap,
                "countable_public_daily": False,
            }
        )
    if not rows:
        return empty
    result = pd.DataFrame(rows).sort_values(
        ["n_stations", "site_ids"], ascending=[False, True]
    ).reset_index(drop=True)
    prefix = f"uk_ea_s{int(cap)}"
    result.insert(
        0,
        "cluster_id",
        [f"{prefix}_{index:03d}" for index in range(1, len(result) + 1)],
    )
    return result[CLUSTER_COLUMNS]


def omit_groups_exceeding_cap(
    clusters: pd.DataFrame,
    *,
    cap_km: float = DEFAULT_CAP_KM,
) -> pd.DataFrame:
    """Omit groups whose max pairwise km exceeds the cap. Do not shrink."""

    if clusters is None or clusters.empty:
        return pd.DataFrame(columns=clusters.columns if clusters is not None else CLUSTER_COLUMNS)
    km = pd.to_numeric(clusters["max_pairwise_km"], errors="coerce")
    keep = km.notna() & km.le(float(cap_km))
    return clusters.loc[keep].copy()


def select_largest_spatial_clusters(
    clusters: pd.DataFrame,
    *,
    n: int = 15,
    cap_km: float = DEFAULT_CAP_KM,
) -> pd.DataFrame:
    """Largest 3+ clusters at the declared cap. Not a T8 list."""

    if clusters is None or clusters.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    frame = clusters.copy()
    if "cap_km" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["cap_km"], errors="coerce").eq(float(cap_km))]
    frame = omit_groups_exceeding_cap(frame, cap_km=cap_km)
    if "n_stations" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["n_stations"], errors="coerce").ge(MIN_STATIONS)]
    return frame.sort_values(
        ["n_stations", "cluster_id"] if "cluster_id" in frame.columns else ["n_stations"],
        ascending=[False, True] if "cluster_id" in frame.columns else [False],
    ).head(int(n)).reset_index(drop=True)


def select_download_site_ids(
    site_ids: list[str],
    stations: pd.DataFrame,
    *,
    max_stations: int = DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER,
) -> list[str]:
    """Choose a download subset. dateOpened is priority only, never a year span.

    River names are not required. UUID hydrometric IDs are tried before
    E-prefixed event monitors because those are more often long series.
    """

    wanted = [str(item).strip() for item in site_ids if str(item).strip()]
    if not wanted:
        return []
    cap = int(max_stations) if max_stations and int(max_stations) > 0 else len(wanted)
    if stations is None or stations.empty or "site_id" not in stations.columns:
        return wanted[:cap]
    members = stations.copy()
    members["site_id"] = members["site_id"].map(lambda value: str(value).strip())
    members = members.loc[members["site_id"].isin(wanted)].drop_duplicates("site_id")
    if members.empty:
        return wanted[:cap]
    members["_uuid"] = members["site_id"].str.contains("-", regex=False)
    members["_event"] = members["site_id"].str.match(r"^E\d", na=False)
    if "date_opened" in members.columns:
        members["_opened"] = pd.to_datetime(members["date_opened"], errors="coerce")
    else:
        members["_opened"] = pd.NaT
    members = members.sort_values(
        ["_uuid", "_event", "_opened", "site_id"],
        ascending=[False, True, True, True],
        na_position="last",
    )
    chosen = [str(item) for item in members["site_id"].head(cap)]
    if len(chosen) < cap:
        extra = [item for item in wanted if item not in chosen]
        chosen.extend(extra[: cap - len(chosen)])
    return chosen


def uk_ea_complete_enough(report: dict[str, Any]) -> bool:
    """Same gate as scripts/65_uk_ea_daily_from_readings.py complete_enough."""

    return bool(
        int(report.get("n_stations") or 0) >= MIN_STATIONS
        and float(report.get("overlap_years") or 0) >= MIN_OVERLAP_YEARS
        and int(report.get("days_with_min_stations") or 0) >= MIN_CONCURRENT_DAYS
    )


def overlap_subset_site_ids(wide: pd.DataFrame, *, min_stations: int = MIN_STATIONS) -> list[str]:
    """Stations that participate in the concurrent-overlap window, if any."""

    if wide is None or wide.empty:
        return []
    counts = wide.notna().sum(axis=1)
    good = counts.ge(int(min_stations))
    if bool(good.any()):
        window = wide.loc[good]
        return [str(column) for column in window.columns if bool(window[column].notna().any())]
    return [str(column) for column in wide.columns if bool(wide[column].notna().any())]


def overlap_subset_max_pairwise_km(
    wide: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    min_stations: int = MIN_STATIONS,
) -> float:
    site_ids = overlap_subset_site_ids(wide, min_stations=min_stations)
    if len(site_ids) < 2 or stations is None or stations.empty:
        return float("nan")
    lookup = stations.drop_duplicates("site_id").copy()
    lookup["site_id"] = lookup["site_id"].map(str)
    lookup = lookup.set_index("site_id")
    lats: list[float] = []
    lons: list[float] = []
    for site_id in site_ids:
        if site_id not in lookup.index:
            continue
        row = lookup.loc[site_id]
        lat = pd.to_numeric(pd.Series([row["latitude"]]), errors="coerce").iloc[0]
        lon = pd.to_numeric(pd.Series([row["longitude"]]), errors="coerce").iloc[0]
        if pd.notna(lat) and pd.notna(lon):
            lats.append(float(lat))
            lons.append(float(lon))
    return max_pairwise_km(lats, lons)


def score_spatial_cluster_overlap(
    wide: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    cap_km: float = DEFAULT_CAP_KM,
    min_stations: int = MIN_STATIONS,
) -> dict[str, Any]:
    """Daily overlap first, then omit if the overlap subset exceeds the cap."""

    report = overlap_report(wide, min_stations=min_stations)
    actual_km = overlap_subset_max_pairwise_km(wide, stations, min_stations=min_stations)
    n_overlap_sites = len(overlap_subset_site_ids(wide, min_stations=min_stations))
    omitted = bool(
        n_overlap_sites >= 2 and pd.notna(actual_km) and float(actual_km) > float(cap_km)
    )
    complete = bool(uk_ea_complete_enough(report) and not omitted)
    report.update(
        {
            "complete_enough": complete,
            "ok": complete,
            "countable_toward_t8": complete,
            "max_pairwise_km_overlap_subset": actual_km,
            "omitted_spatial_cap": omitted,
            "distance_cap_km": float(cap_km),
            "continent": "europe",
            "derived_from": "uk_ea_subdaily_readings_daily_mean",
            "catalog_cluster_is_not_t8": True,
            "date_opened_not_daily_year_span": True,
        }
    )
    return report


def w6_europe_spatial_manifest(
    *,
    n_stations_catalog: int,
    n_with_river_name: int,
    n_spatial_clusters_3plus_50km: int,
    n_spatial_clusters_3plus_100km: int,
    n_clusters_downloaded: int,
    n_complete_enough: int,
    n_hydrometric_stations: int | None = None,
    n_event_monitor_stations: int | None = None,
    n_hydrometric_spatial_clusters_3plus_50km: int | None = None,
) -> dict[str, Any]:
    """Locked W6 Europe UK EA spatial overlap/QC keys. Hub'Eau Correcte stays unused."""

    n_complete = int(n_complete_enough)
    passed = bool(n_complete > 0)
    return {
        "what_this_is": (
            "UK EA spatial (lat/lon) clustering and daily-mean overlap QC for "
            "W6 Europe. Catalog groups use complete-linkage with a 50 km max "
            "pairwise geodesic cap; 100 km is a sensitivity count only. "
            "The first W6 pass downloaded the largest 15 all-catalog 50 km "
            "clusters (event-monitor IDs included, hydrometric IDs preferred)."
        ),
        "what_this_is_not": (
            "Not a river-name cluster. Not T8 unless complete_enough. "
            "dateOpened is not a daily-year span. Catalog 3+ groups are not T8. "
            "100 km counts are not T8. Not Hub'Eau Sandre Correcte. Not Loire. "
            "Not sealed temperatures. Not T2 even if passed."
        ),
        "n_stations_catalog": int(n_stations_catalog),
        "n_with_river_name": int(n_with_river_name),
        "n_spatial_clusters_3plus_50km": int(n_spatial_clusters_3plus_50km),
        "n_spatial_clusters_3plus_100km": int(n_spatial_clusters_3plus_100km),
        "n_hydrometric_stations": n_hydrometric_stations,
        "n_event_monitor_stations": n_event_monitor_stations,
        "n_hydrometric_spatial_clusters_3plus_50km": n_hydrometric_spatial_clusters_3plus_50km,
        "event_monitors_not_used_for_t8_download": False,
        "n_clusters_downloaded": int(n_clusters_downloaded),
        "n_complete_enough": n_complete,
        "countable_toward_t8": bool(n_complete > 0),
        "hubeau_correcte_t8_usable": False,
        "hubeau_code4_not_relabeled_as_correcte": True,
        "hubeau_n_sites_with_sandre_correcte_observations": 0,
        "hubeau_bulk_daily_downloads_started": 0,
        "hubeau_sandre_correcte_note": HUBEAU_SANDRE_CORRECTE_NOTE,
        "europe_daily_years_invented": False,
        "loire_downloaded": False,
        "sealed_outcomes_opened": False,
        "formal_evidence": False,
        "passed": passed,
        "temporal_resolution_source": "subdaily_resampled_to_daily_mean",
        "spatial_cap_km": DEFAULT_CAP_KM,
        "spatial_sensitivity_cap_km": SENSITIVITY_CAP_KM,
        "grouping": "complete_linkage_max_pairwise_geodesic",
        "river_name_required": False,
        "date_opened_used_as_daily_span": False,
        "n_stations_per_cluster_download_cap": DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER,
    }


__all__ = [
    "CLUSTER_COLUMNS",
    "DEFAULT_CAP_KM",
    "DEFAULT_DOWNLOAD_STATIONS_PER_CLUSTER",
    "HUBEAU_SANDRE_CORRECTE_NOTE",
    "MIN_CONCURRENT_DAYS",
    "MIN_OVERLAP_YEARS",
    "MIN_STATIONS",
    "SENSITIVITY_CAP_KM",
    "EVENT_MONITOR_SITE_ID",
    "cluster_uk_ea_spatial",
    "hydrometric_stations",
    "is_hydrometric_site_id",
    "max_pairwise_km",
    "omit_groups_exceeding_cap",
    "overlap_subset_max_pairwise_km",
    "overlap_subset_site_ids",
    "pairwise_geodesic_km",
    "score_spatial_cluster_overlap",
    "select_download_site_ids",
    "select_largest_spatial_clusters",
    "uk_ea_complete_enough",
    "w6_europe_spatial_manifest",
]
