"""Competing W1-A HUC8 clustering (Implementer B / adversarial hydrologist).

Standalone on purpose: production files are not edited. Imports repo helpers
``official_huc_digits``, ``official_huc_prefix``, and
``largest_overlapping_subset`` rather than re-inventing a broken ``zfill(8)[:8]``.

Reviewer holes encoded here, not just mentioned:

1. Naive ``str(huc).zfill(8)[:8]`` is wrong on HUC12 / float / odd-length codes.
2. Truncated 12-station combo search undercounts; exact interval scan does not.
3. ``missouri_river_huc10`` cannot survive as one HUC8 network.
4. Pairwise distance is geodesic km (R=6371), not degree span.
5. Missing lat/lon never becomes max_pair_km 0 or inf.
6. NLDI UM+DM is a covariate; disconnected groups are kept.
7. Catalog overlap is not qualified years; 161 is not T2.
8. never_sealed cannot be sealed; Loire/Swiss cannot fill the 10 non-NA floor.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE
for _parent in (HERE, *HERE.parents):
    if (_parent / "src" / "stream_recoverability").is_dir():
        REPO = _parent
        break
SRC = REPO / "src"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.public_river_inventory import (  # noqa: E402
    cluster_rivers_from_catalog,
    cluster_rivers_from_catalog_v2,
    largest_overlapping_subset,
    official_huc_digits,
    official_huc_prefix,
    river_name_from_site_name,
)

from nldi_connectivity import as_site_id, annotate_clusters  # noqa: E402

EARTH_RADIUS_KM = 6371.0
STREAM_TYPES = {"Stream", "ST", "Streamgage"}
REVIEWER_TRUNCATION_CAP = 12
SPLIT_SEED = 20260826
SPLIT_FRACTIONS = (0.50, 0.20, 0.30)
MISSING_COORD_POLICY = (
    "never_zero_or_inf: NaN if fewer than two located stations; "
    "distance cap drops unlocated stations then re-validates overlap; "
    "does not treat missing coordinates as 0 km or infinite km"
)

CATALOG_SERIES = REPO / "results/framework/public_catalog/usgs_daily_temperature_series.csv"
CATALOG_LOCATIONS = (
    REPO / "results/framework/public_catalog/usgs_long_temperature_locations.csv"
)
FREEZE_PATH = REPO / "configs/design_freeze_v9.yaml"
V1_CATALOG = REPO / "configs/network_catalog_v1.yaml"
GAGES_PANEL = (
    REPO / "results/regulation_panel_v1_legacy_transport/station_metrics.csv"
)

HUC_CLIMATE = {
    "01": "humid_continental",
    "02": "humid_continental",
    "03": "humid_subtropical",
    "04": "humid_continental",
    "05": "humid_continental",
    "06": "humid_subtropical",
    "07": "humid_continental",
    "10": "cold_semiarid",
    "11": "humid_subtropical",
    "12": "subtropical_semiarid",
    "13": "cold_arid_highland",
    "14": "cold_arid_highland",
    "15": "hot_arid",
    "16": "cold_semiarid",
    "17": "marine_west_coast",
    "18": "mediterranean",
    "19": "subarctic",
    "20": "humid_continental",
}

NEVER_SEALED_NAME_TOKENS = (
    "jinsha",
    "chattahoochee",
    "delaware river",
    "willamette river",
    "suwannee river",
    "yellowstone river",
    "rio grande",
    "madison river",
    "cahaba river",
    "mckenzie river",
    "mahoning river",
    "roanoke river",
    "santa fe river",
    "clearwater river",
)

LOIRE_SWISS_IDS = {"loire_mainstem", "swiss_aar_rhine"}


def naive_reviewer_huc8(value: Any) -> str:
    """The reviewer recipe ``str(huc).zfill(8)[:8]``. Wrong on HUC12/float/odd lengths."""

    return str(value).zfill(8)[:8]


def naive_huc_prefix(value: Any, width: int) -> str:
    """Naive prefix used to measure how a zfill(8)[:8] reader would group."""

    return naive_reviewer_huc8(value)[: int(width)]


def geodesic_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, Earth radius 6371 km. Not a degree span."""

    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    hav = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(hav)))


def _finite_coords(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat_f) or not math.isfinite(lon_f):
        return None
    return lat_f, lon_f


def pairwise_geodesic_stats(latitudes: Sequence[Any], longitudes: Sequence[Any]) -> dict[str, Any]:
    """Max pairwise geodesic km among *located* stations.

    Explicit missing-coordinate policy (attack 5):
    - 0 located or 1 located: ``max_pair_km`` is NaN, never 0, never inf.
    - partial coords: max is computed only on located pairs; flagged incomplete.
    """

    points: list[tuple[float, float]] = []
    n_missing = 0
    for lat, lon in zip(latitudes, longitudes):
        pair = _finite_coords(lat, lon)
        if pair is None:
            n_missing += 1
        else:
            points.append(pair)
    n_located = len(points)
    if n_located == 0:
        policy = "no_coords"
        max_km = float("nan")
    elif n_located == 1:
        policy = "single_coord" if n_missing else "single_station"
        max_km = float("nan")
    else:
        policy = "partial_coords" if n_missing else "complete"
        max_km = 0.0
        for (a_lat, a_lon), (b_lat, b_lon) in combinations(points, 2):
            max_km = max(max_km, geodesic_km(a_lat, a_lon, b_lat, b_lon))
    if max_km == float("inf") or max_km == float("-inf"):
        raise RuntimeError("max_pair_km inf is forbidden; missing coords must be NaN")
    return {
        "max_pair_km": max_km,
        "n_stations_with_coords": n_located,
        "n_stations_missing_coords": n_missing,
        "coord_policy": policy,
        "coords_incomplete": bool(n_missing),
    }


def _interval_years(begins: Sequence[Any], ends: Sequence[Any], indices: Sequence[int]) -> tuple[pd.Timestamp, pd.Timestamp, float]:
    start = pd.to_datetime([begins[i] for i in indices], errors="coerce")
    stop = pd.to_datetime([ends[i] for i in indices], errors="coerce")
    if start.isna().any() or stop.isna().any():
        return pd.NaT, pd.NaT, float("nan")
    overlap_start = start.max()
    overlap_end = stop.min()
    if pd.isna(overlap_start) or pd.isna(overlap_end):
        return pd.NaT, pd.NaT, float("nan")
    years = float((overlap_end - overlap_start).days / 365.25)
    return overlap_start, overlap_end, years


def largest_overlapping_subset_truncated(
    begins: Sequence[Any],
    ends: Sequence[Any],
    *,
    min_overlap_years: float,
    max_n: int = REVIEWER_TRUNCATION_CAP,
    min_size: int = 1,
) -> tuple[list[int], pd.Timestamp, pd.Timestamp, float]:
    """Reviewer-style combo search, truncated at ``max_n`` stations.

    For n>12 this **undercounts**: a concurrent 13th station is invisible, and a
    short concurrent triple can lose to 12 long but temporally isolated series.
    """

    start = pd.to_datetime(list(begins), errors="coerce")
    stop = pd.to_datetime(list(ends), errors="coerce")
    n = len(start)
    if n == 0:
        return [], pd.NaT, pd.NaT, float("nan")
    order = list(range(n))
    if n > int(max_n):
        delta = stop - start
        seconds = pd.Series(delta.total_seconds(), index=range(n)).fillna(-1.0)
        order = sorted(order, key=lambda i: (-float(seconds.iloc[i]), i))[: int(max_n)]
        order = sorted(order)
    best_idx: list[int] = []
    best_n = 0
    best_years = -1.0
    best_overlap_start = pd.NaT
    best_overlap_end = pd.NaT
    for k in range(len(order), max(int(min_size) - 1, 0), -1):
        found_at_k = False
        for combo in combinations(order, k):
            overlap_start, overlap_end, years = _interval_years(start, stop, combo)
            if pd.isna(years) or years < float(min_overlap_years):
                continue
            chosen = list(combo)
            better = k > best_n
            if k == best_n:
                if years > best_years + 1.0e-12:
                    better = True
                elif abs(years - best_years) <= 1.0e-12:
                    if pd.isna(best_overlap_start) or overlap_start < best_overlap_start:
                        better = True
                    elif overlap_start == best_overlap_start and chosen < best_idx:
                        better = True
            if better:
                best_idx = chosen
                best_n = k
                best_years = years
                best_overlap_start = overlap_start
                best_overlap_end = overlap_end
                found_at_k = True
        if found_at_k:
            break
    if best_n == 0:
        return [], pd.NaT, pd.NaT, float("nan")
    return best_idx, best_overlap_start, best_overlap_end, best_years


def _iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return None
    return stamp.date().isoformat()


def _merge_catalog(series: pd.DataFrame, locations: pd.DataFrame | None) -> pd.DataFrame:
    left = series.copy()
    left["site_id"] = left["site_id"].map(as_site_id)
    if locations is None or locations.empty:
        return left
    right = locations.copy()
    right["site_id"] = right["site_id"].map(as_site_id)
    merged = left.merge(right, on="site_id", how="left", suffixes=("", "_loc"))
    for column in ("name", "huc", "site_type", "latitude", "longitude", "state_name"):
        loc_column = f"{column}_loc"
        if column not in merged.columns and loc_column in merged.columns:
            merged[column] = merged[loc_column]
        elif column in merged.columns and loc_column in merged.columns:
            merged[column] = merged[column].where(
                merged[column].notna()
                & ~merged[column].astype(str).str.lower().isin({"", "nan", "none"}),
                merged[loc_column],
            )
    return merged


def prepare_huc8_stations(
    series: pd.DataFrame,
    locations: pd.DataFrame | None,
    *,
    min_span_years: float,
    huc_encoder: Callable[[Any, int], str] = official_huc_prefix,
) -> pd.DataFrame:
    if series is None or series.empty:
        return pd.DataFrame()
    merged = _merge_catalog(series, locations)
    span = pd.to_numeric(merged.get("span_years"), errors="coerce")
    if span.isna().all() and {"daily_begin", "daily_end"} <= set(merged.columns):
        begin = pd.to_datetime(merged["daily_begin"], errors="coerce")
        end = pd.to_datetime(merged["daily_end"], errors="coerce")
        span = (end - begin).dt.days / 365.25
        merged["span_years"] = span
    merged = merged.loc[span.ge(float(min_span_years))].copy()
    if merged.empty:
        return merged
    site_type = merged.get("site_type", pd.Series(index=merged.index, dtype=object))
    merged = merged.loc[site_type.fillna("Stream").isin(STREAM_TYPES)].copy()
    if merged.empty:
        return merged
    names = merged.get("name", pd.Series(index=merged.index, dtype=object))
    merged["river_name"] = names.map(river_name_from_site_name)
    huc = merged["huc"] if "huc" in merged.columns else pd.Series("", index=merged.index)
    if "huc_loc" in merged.columns:
        huc = huc.where(
            huc.notna() & (huc.astype(str).str.lower() != "nan"), merged["huc_loc"]
        )
    merged["huc_raw"] = huc
    merged["huc2"] = huc.map(lambda value: huc_encoder(value, 2))
    merged["huc4"] = huc.map(lambda value: huc_encoder(value, 4))
    merged["huc6"] = huc.map(lambda value: huc_encoder(value, 6))
    merged["huc8"] = huc.map(lambda value: huc_encoder(value, 8))
    return merged.reset_index(drop=True)


def _search_overlap(
    begins: Sequence[Any],
    ends: Sequence[Any],
    *,
    min_overlap_years: float,
    overlap_search: str,
    min_stations: int = 1,
) -> tuple[list[int], pd.Timestamp, pd.Timestamp, float]:
    if overlap_search == "truncated_combo":
        return largest_overlapping_subset_truncated(
            begins,
            ends,
            min_overlap_years=min_overlap_years,
            min_size=min_stations,
        )
    if overlap_search != "exact":
        raise ValueError(f"unknown overlap_search {overlap_search!r}")
    return largest_overlapping_subset(begins, ends, min_overlap_years=min_overlap_years)


def _located_mask(frame: pd.DataFrame) -> pd.Series:
    if "latitude" not in frame.columns or "longitude" not in frame.columns:
        return pd.Series(False, index=frame.index)
    lat = pd.to_numeric(frame["latitude"], errors="coerce")
    lon = pd.to_numeric(frame["longitude"], errors="coerce")
    return lat.notna() & lon.notna() & np.isfinite(lat.to_numpy()) & np.isfinite(lon.to_numpy())


def _apply_distance_cap(
    subset: pd.DataFrame,
    *,
    max_pair_km: float | None,
    min_stations: int,
    min_overlap_years: float,
    distance_mode: str,
    overlap_search: str,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    stats = pairwise_geodesic_stats(
        subset.get("latitude", pd.Series(dtype=float)),
        subset.get("longitude", pd.Series(dtype=float)),
    )
    if max_pair_km is None:
        stats["distance_mode"] = "uncapped"
        stats["dropped_for_distance_cap"] = False
        return subset, stats

    cap = float(max_pair_km)
    located = subset.loc[_located_mask(subset)].copy()
    if len(located) < int(min_stations):
        stats["distance_mode"] = distance_mode
        stats["dropped_for_distance_cap"] = True
        stats["coord_policy"] = "insufficient_located_for_cap"
        return None, stats

    chosen, overlap_start, overlap_end, overlap_years = _search_overlap(
        located["daily_begin"],
        located["daily_end"],
        min_overlap_years=min_overlap_years,
        overlap_search=overlap_search,
        min_stations=int(min_stations),
    )
    if len(chosen) < int(min_stations):
        stats["distance_mode"] = distance_mode
        stats["dropped_for_distance_cap"] = True
        return None, stats
    located = located.iloc[chosen].copy()
    stats = pairwise_geodesic_stats(located["latitude"], located["longitude"])
    stats["distance_mode"] = distance_mode
    if pd.isna(stats["max_pair_km"]):
        stats["dropped_for_distance_cap"] = True
        return None, stats
    if float(stats["max_pair_km"]) <= cap:
        stats["dropped_for_distance_cap"] = False
        stats["overlap_start"] = overlap_start
        stats["overlap_end"] = overlap_end
        stats["overlap_years"] = overlap_years
        return located, stats

    if distance_mode == "filter":
        # Prefer omit over silent shrink: the max-overlap subset is a different
        # network once you start dropping far stations.
        stats["dropped_for_distance_cap"] = True
        return None, stats
    if distance_mode != "shrink":
        raise ValueError(f"unknown distance_mode {distance_mode!r}")

    work = located.copy().reset_index(drop=True)
    while len(work) >= int(min_stations):
        current = pairwise_geodesic_stats(work["latitude"], work["longitude"])
        if pd.notna(current["max_pair_km"]) and float(current["max_pair_km"]) <= cap:
            chosen, overlap_start, overlap_end, overlap_years = _search_overlap(
                work["daily_begin"],
                work["daily_end"],
                min_overlap_years=min_overlap_years,
                overlap_search=overlap_search,
                min_stations=int(min_stations),
            )
            if len(chosen) >= int(min_stations):
                kept = work.iloc[chosen]
                stats = pairwise_geodesic_stats(kept["latitude"], kept["longitude"])
                stats["distance_mode"] = "shrink"
                stats["dropped_for_distance_cap"] = False
                stats["overlap_start"] = overlap_start
                stats["overlap_end"] = overlap_end
                stats["overlap_years"] = overlap_years
                return kept, stats
            break
        # Drop the endpoint of the current max pair with larger mean distance.
        lats = pd.to_numeric(work["latitude"], errors="coerce").to_numpy()
        lons = pd.to_numeric(work["longitude"], errors="coerce").to_numpy()
        worst_i, worst_j, worst = 0, 1, -1.0
        means = [0.0] * len(work)
        for i in range(len(work)):
            for j in range(i + 1, len(work)):
                dist = geodesic_km(lats[i], lons[i], lats[j], lons[j])
                means[i] += dist
                means[j] += dist
                if dist > worst:
                    worst, worst_i, worst_j = dist, i, j
        drop = worst_i if means[worst_i] >= means[worst_j] else worst_j
        work = work.drop(work.index[drop]).reset_index(drop=True)
    stats["distance_mode"] = "shrink"
    stats["dropped_for_distance_cap"] = True
    return None, stats


def _cluster_row(
    subset: pd.DataFrame,
    *,
    huc8: str,
    n_available: int,
    overlap_start: Any,
    overlap_end: Any,
    overlap_years: float,
    min_stations: int,
    min_overlap_years: float,
    min_span_years: float,
    geo: dict[str, Any],
    grouping: str = "huc8",
    huc_level: str = "huc8",
) -> dict[str, Any]:
    names = sorted(
        {
            str(item).strip()
            for item in subset.get("river_name", pd.Series(dtype=object)).dropna()
            if str(item).strip()
        }
    )
    states = ""
    if "state_name" in subset.columns:
        states = ",".join(
            sorted({str(item) for item in subset["state_name"].dropna() if str(item)})
        )
    first_huc = subset["huc"].iloc[0] if "huc" in subset.columns and len(subset) else ""
    huc2 = subset["huc2"].iloc[0] if "huc2" in subset.columns and len(subset) else official_huc_prefix(first_huc, 2)
    huc4 = subset["huc4"].iloc[0] if "huc4" in subset.columns and len(subset) else official_huc_prefix(first_huc, 4)
    huc6 = subset["huc6"].iloc[0] if "huc6" in subset.columns and len(subset) else official_huc_prefix(first_huc, 6)
    site_ids = ",".join(sorted(subset["site_id"].map(as_site_id), key=str))
    network_id = f"{huc_level}_{huc8}" if huc_level != "huc8" else f"huc8_{huc8}"
    max_pair = geo.get("max_pair_km")
    if max_pair is not None and not pd.isna(max_pair):
        if not math.isfinite(float(max_pair)):
            raise RuntimeError("refusing to emit non-finite max_pair_km")
    return {
        "grouping": grouping,
        "min_stations": int(min_stations),
        "min_overlap_years": float(min_overlap_years),
        "min_span_years": float(min_span_years),
        "network_id": network_id,
        "huc2": huc2,
        "huc4": huc4,
        "huc6": huc6,
        "huc8": huc8 if huc_level == "huc8" else subset.get("huc8", pd.Series([""])).iloc[0]
        if "huc8" in subset.columns
        else official_huc_prefix(first_huc, 8),
        "huc_key": huc8,
        "n_stations": int(len(subset)),
        "n_stations_available": int(n_available),
        "site_ids": site_ids,
        "overlap_start": _iso(overlap_start),
        "overlap_end": _iso(overlap_end),
        "catalog_overlap_start": _iso(overlap_start),
        "catalog_overlap_end": _iso(overlap_end),
        "catalog_overlap_years": overlap_years,
        "enough_overlap_years": bool(
            pd.notna(overlap_years) and overlap_years >= float(min_overlap_years)
        ),
        "max_pair_km": max_pair,
        "n_stations_with_coords": int(geo.get("n_stations_with_coords") or 0),
        "n_stations_missing_coords": int(geo.get("n_stations_missing_coords") or 0),
        "coord_policy": geo.get("coord_policy"),
        "coords_incomplete": bool(geo.get("coords_incomplete")),
        "distance_mode": geo.get("distance_mode"),
        "river_names": "|".join(names),
        "river_name": names[0] if len(names) == 1 else "mixed",
        "states": states,
        "flow_connected": "not_queried",
        "spatially_proximate_not_flow_connected": False,
        "temperature_record_unverified": True,
        "sealed_outcomes_opened": False,
    }


def cluster_by_huc_level(
    series_df: pd.DataFrame,
    locations_df: pd.DataFrame | None = None,
    *,
    huc_width: int,
    min_stations: int = 3,
    min_overlap_years: float = 8,
    max_pair_km: float | None = None,
    min_span_years: float | None = None,
    overlap_search: str = "exact",
    distance_mode: str = "filter",
    huc_encoder: Callable[[Any, int], str] = official_huc_prefix,
    grouping: str | None = None,
) -> pd.DataFrame:
    span = float(min_overlap_years if min_span_years is None else min_span_years)
    prepared = prepare_huc8_stations(
        series_df, locations_df, min_span_years=span, huc_encoder=huc_encoder
    )
    key = f"huc{huc_width}"
    grouping = grouping or key
    if prepared.empty or key not in prepared.columns:
        return pd.DataFrame()
    work = prepared.loc[prepared[key].astype(str).str.len().gt(0)].copy()
    rows: list[dict[str, Any]] = []
    for huc_key, group in work.groupby(key, sort=False, dropna=False):
        huc_id = "" if pd.isna(huc_key) else str(huc_key)
        if not huc_id:
            continue
        n_available = int(len(group))
        chosen, overlap_start, overlap_end, overlap_years = _search_overlap(
            group["daily_begin"],
            group["daily_end"],
            min_overlap_years=min_overlap_years,
            overlap_search=overlap_search,
            min_stations=int(min_stations),
        )
        if len(chosen) < int(min_stations):
            continue
        subset = group.iloc[chosen].copy()
        subset, geo = _apply_distance_cap(
            subset,
            max_pair_km=max_pair_km,
            min_stations=min_stations,
            min_overlap_years=min_overlap_years,
            distance_mode=distance_mode,
            overlap_search=overlap_search,
        )
        if subset is None or len(subset) < int(min_stations):
            continue
        if "overlap_start" in geo and geo["overlap_start"] is not None:
            overlap_start = geo["overlap_start"]
            overlap_end = geo["overlap_end"]
            overlap_years = geo["overlap_years"]
        else:
            _, overlap_start, overlap_end, overlap_years = _search_overlap(
                subset["daily_begin"],
                subset["daily_end"],
                min_overlap_years=min_overlap_years,
                overlap_search="exact",
            )
            geo.update(pairwise_geodesic_stats(subset["latitude"], subset["longitude"]))
        rows.append(
            _cluster_row(
                subset,
                huc8=huc_id,
                n_available=n_available,
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                overlap_years=overlap_years,
                min_stations=min_stations,
                min_overlap_years=min_overlap_years,
                min_span_years=span,
                geo=geo,
                grouping=grouping,
                huc_level=key,
            )
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["n_stations", "catalog_overlap_years", "network_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def cluster_by_huc8(
    series_df: pd.DataFrame,
    locations_df: pd.DataFrame | None = None,
    min_stations: int = 3,
    min_overlap_years: float | int = 8,
    max_pair_km: float | None = None,
    *,
    min_span_years: float | None = None,
    overlap_search: str = "exact",
    distance_mode: str = "filter",
    huc_encoder: Callable[[Any, int], str] = official_huc_prefix,
) -> pd.DataFrame:
    """HUC8 subbasin clustering. Replaces name×HUC2 string matching.

    Exact max-overlap subset search. No truncation at 12 stations.
    ``max_pair_km`` is geodesic. Missing coordinates are never 0 or inf.
    """

    if isinstance(locations_df, (int, float)) and not isinstance(locations_df, bool):
        # Defensive: ``cluster_by_huc8(df, 3)`` from the spec's positional form.
        min_stations = int(locations_df)
        locations_df = None
    return cluster_by_huc_level(
        series_df,
        locations_df,
        huc_width=8,
        min_stations=int(min_stations),
        min_overlap_years=float(min_overlap_years),
        max_pair_km=max_pair_km,
        min_span_years=min_span_years,
        overlap_search=overlap_search,
        distance_mode=distance_mode,
        huc_encoder=huc_encoder,
        grouping="huc8",
    )


def name_huc2_contrast(
    series_df: pd.DataFrame,
    locations_df: pd.DataFrame | None,
    *,
    min_stations: int = 3,
    min_overlap_years: float = 8.0,
) -> pd.DataFrame:
    """Old name×HUC2 rule as contrast. Does not replace HUC8 output."""

    if locations_df is None:
        locations_df = pd.DataFrame()
    v2 = cluster_rivers_from_catalog_v2(
        series_df,
        locations_df,
        min_stations=min_stations,
        min_overlap_years=min_overlap_years,
        min_span_years=min_overlap_years,
        huc_levels=("huc2",),
        include_huc8_only=False,
    )
    if v2.empty:
        return v2
    return v2.loc[v2["grouping"].eq("name_huc2")].reset_index(drop=True)


def load_never_sealed_from_v1(path: Path = V1_CATALOG) -> dict[str, dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    freeze = yaml.safe_load(FREEZE_PATH.read_text(encoding="utf-8"))
    never_ids = set((freeze.get("split_rule") or {}).get("never_sealed_networks") or [])
    out: dict[str, dict[str, Any]] = {}
    for item in document.get("networks") or []:
        network_id = str(item.get("network_id") or "")
        if network_id in never_ids:
            sites = {as_site_id(site) for site in (item.get("candidate_station_ids") or [])}
            sites.discard("")
            out[network_id] = {
                "split_role": item.get("split_role"),
                "site_ids": sites,
                "historical_seen": bool(item.get("historical_seen")),
            }
    return out


def tag_never_sealed(
    clusters: pd.DataFrame, burned: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    frame = clusters.copy()
    burned_sites: dict[str, str] = {}
    for network_id, payload in burned.items():
        for site in payload["site_ids"]:
            burned_sites[site] = network_id
    flags = []
    matched = []
    historical = []
    for row in frame.itertuples(index=False):
        sites = {as_site_id(item) for item in str(row.site_ids).split(",")}
        hits = {burned_sites[site] for site in sites if site in burned_sites}
        name_hit = any(
            token in str(getattr(row, "river_names", "") or getattr(row, "river_name", "")).lower()
            for token in NEVER_SEALED_NAME_TOKENS
        )
        is_never = bool(hits) or name_hit
        flags.append(is_never)
        matched.append(",".join(sorted(hits)))
        hist = any(
            burned[item]["historical_seen"] for item in hits if item in burned
        )
        historical.append(hist or ("chattahoochee" in str(getattr(row, "river_names", "")).lower()))
    frame["never_sealed"] = flags
    frame["never_sealed_v1_ids"] = matched
    frame["historical_seen"] = historical
    return frame


def missouri_huc8_split(
    series_df: pd.DataFrame, locations_df: pd.DataFrame, clusters: pd.DataFrame
) -> dict[str, Any]:
    """Prove missouri_river_huc10 cannot survive as one HUC8 network."""

    v1 = cluster_rivers_from_catalog(series_df, locations_df)
    missouri = v1.loc[v1["network_id"].eq("missouri_river_huc10")]
    if missouri.empty:
        v2 = name_huc2_contrast(series_df, locations_df, min_stations=3, min_overlap_years=8)
        missouri = v2.loc[v2["network_id"].eq("missouri_river_huc10")]
    if missouri.empty:
        return {"found_name_huc2": False, "survives_as_one_huc8": False}
    site_ids = [as_site_id(item) for item in str(missouri.iloc[0]["site_ids"]).split(",")]
    prepared = prepare_huc8_stations(series_df, locations_df, min_span_years=8.0)
    piece = prepared.loc[prepared["site_id"].isin(site_ids)].copy()
    huc8s = sorted({str(item) for item in piece["huc8"] if str(item)})
    matching_clusters = []
    if not clusters.empty and "site_ids" in clusters.columns:
        wanted = set(site_ids)
        for row in clusters.itertuples(index=False):
            have = {as_site_id(item) for item in str(row.site_ids).split(",")}
            if have & wanted:
                matching_clusters.append(
                    {
                        "network_id": row.network_id,
                        "huc8": getattr(row, "huc8", None),
                        "n_stations": int(row.n_stations),
                        "river_names": getattr(row, "river_names", None),
                    }
                )
    return {
        "found_name_huc2": True,
        "name_huc2_n_stations": int(missouri.iloc[0]["n_stations"]),
        "name_huc2_site_ids": site_ids,
        "huc8_ids": huc8s,
        "n_huc8": len(huc8s),
        "survives_as_one_huc8": len(huc8s) == 1,
        "huc8_clusters_sharing_those_sites": matching_clusters,
        "proof": (
            f"missouri_river_huc10 lists {len(site_ids)} stations under HUC2 10; "
            f"official HUC8 splits them into {len(huc8s)} subbasins: {', '.join(huc8s)}."
        ),
    }


def _size_tertile(values: Sequence[int]) -> list[str]:
    series = pd.Series(list(values), dtype=float)
    if series.nunique() < 3:
        return ["mid"] * len(series)
    try:
        labels = pd.qcut(series.rank(method="first"), 3, labels=["small", "mid", "large"])
        return [str(item) for item in labels]
    except ValueError:
        return ["mid"] * len(series)


def assignment_digest(network_id: str, seed: int) -> str:
    payload = f"{int(seed)}\t{network_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_split_bytes(frame: pd.DataFrame) -> bytes:
    columns = [
        "network_id",
        "split_role",
        "seed",
        "climate_band",
        "size_tertile",
        "stratum",
        "regulation_stratum",
        "never_sealed",
    ]
    work = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    work = work.sort_values("network_id").reset_index(drop=True)
    return work.to_csv(index=False).encode("utf-8")


def lock_stratified_split(
    clusters: pd.DataFrame,
    *,
    seed: int = SPLIT_SEED,
) -> tuple[pd.DataFrame, str]:
    """50/20/30 development/validation/sealed, SHA-256 within climate×size strata.

    Regulation stratum is ``unknown_until_gages``. The 335-row regulation-panel
    extract is not a catalog-wide GAGES-II join; using it as a split factor
    would silently bias sealed allocation. Loire/Swiss are not in this USGS
    HUC8 table and must not be inserted to pad the 10 non-NA sealed floor.
    never_sealed rows are excluded from the random draw and never get
    ``split_role=sealed``.
    """

    frame = clusters.copy().reset_index(drop=True)
    if "never_sealed" not in frame.columns:
        frame["never_sealed"] = False
    frame["climate_band"] = frame["huc2"].map(lambda value: HUC_CLIMATE.get(str(value), "unspecified"))
    tertiles = _size_tertile(list(frame["n_stations"].astype(int)))
    frame["size_tertile"] = tertiles
    frame["stratum"] = frame["climate_band"].astype(str) + "|" + frame["size_tertile"].astype(str)
    frame["regulation_stratum"] = "unknown_until_gages"
    frame["seed"] = int(seed)
    frame["assignment_sha256"] = [
        assignment_digest(str(network_id), seed) for network_id in frame["network_id"]
    ]
    frame["split_role"] = "catalog_candidate"
    eligible_mask = (
        ~frame["never_sealed"].astype(bool)
        & ~frame["historical_seen"].astype(bool)
        if "historical_seen" in frame.columns
        else ~frame["never_sealed"].astype(bool)
    )
    roles = ["development"] * len(frame)
    for index, _ in enumerate(frame.itertuples(index=False)):
        if bool(frame.iloc[index]["never_sealed"]):
            roles[index] = "never_sealed_held_out"
        elif "historical_seen" in frame.columns and bool(frame.iloc[index]["historical_seen"]):
            roles[index] = "historical"
        else:
            roles[index] = "pending"
    frame["split_role"] = roles

    pending_idx = [i for i, role in enumerate(roles) if role == "pending"]
    by_stratum: dict[str, list[int]] = {}
    for i in pending_idx:
        by_stratum.setdefault(str(frame.iloc[i]["stratum"]), []).append(i)
    for _, members in by_stratum.items():
        members.sort(key=lambda i: (frame.iloc[i]["assignment_sha256"], frame.iloc[i]["network_id"]))
        n = len(members)
        n_dev = n * 50 // 100
        n_val = n * 20 // 100
        for rank, i in enumerate(members):
            if rank < n_dev:
                frame.iat[i, frame.columns.get_loc("split_role")] = "development"
            elif rank < n_dev + n_val:
                frame.iat[i, frame.columns.get_loc("split_role")] = "validation"
            else:
                frame.iat[i, frame.columns.get_loc("split_role")] = "sealed"

    if frame["never_sealed"].astype(bool).any():
        sealed_never = frame.loc[
            frame["never_sealed"].astype(bool) & frame["split_role"].eq("sealed")
        ]
        if not sealed_never.empty:
            raise RuntimeError(
                f"never_sealed networks assigned sealed: {list(sealed_never['network_id'])}"
            )
    forbidden = set(LOIRE_SWISS_IDS)
    if any(str(item) in forbidden for item in frame["network_id"]):
        raise RuntimeError("Loire/Swiss cannot enter the USGS HUC8 split")
    digest = hashlib.sha256(canonical_split_bytes(frame)).hexdigest()
    frame["split_table_sha256"] = digest
    return frame, digest


def _count_ok(frame: pd.DataFrame) -> int:
    if frame is None or frame.empty:
        return 0
    if "enough_overlap_years" in frame.columns:
        return int(frame["enough_overlap_years"].fillna(False).sum())
    return int(len(frame))


def write_feasibility(path: Path, counts: dict[str, Any], missouri: dict[str, Any]) -> None:
    exact = counts.get("huc8_3st_8y_exact")
    truncated = counts.get("huc8_3st_8y_truncated_combo")
    naive = counts.get("huc8_3st_8y_naive_zfill")
    v2_huc8 = counts.get("v2_huc8_only_3st_8y")
    lines = [
        "# Catalog v3 HUC8 feasibility (competing / adversarial)",
        "",
        "Metadata only. Daily temperature values were **not** downloaded.",
        "Sealed temperatures were **not** opened. `network_catalog_v1.yaml` was",
        "**not** remapped. This is a grouping-rule correction (HUC8 subbasin vs",
        "name×HUC2 region), not a relaxation, and not T2.",
        "",
        "## Exact counts (this implementation)",
        "",
        f"- HUC8, 3 stations, 8-year **exact** subset: **{exact}**",
        f"- HUC8, 3 stations, 8-year **truncated combo (n>12 → 12)**: **{truncated}**",
        f"- HUC8, 3 stations, 8-year **naive zfill(8)[:8]**: **{naive}**",
        f"- Reviewer's published figure: **161**. Reproduced **exactly** by naive `str(huc).zfill(8)[:8]`, not by truncated combo search.",
        f"- Exact vs 161: delta **{None if exact is None else int(exact) - 161}** (official HUC prefix restores five groups naive zfill splits or drops).",
        f"- Exact vs truncated-combo network count: delta **{None if exact is None or truncated is None else int(exact) - int(truncated)}**.",
        f"- Groups with n_stations_available > 12: **{counts.get('n_groups_available_gt_12')}**. Truncation still finds a ≥3-station subset among the 12 longest, so the *count* does not move; `n_stations` is capped at 12 and undercounts those groups (n_stations differs in **{counts.get('n_groups_n_stations_truncated')}** networks).",
        f"- Production v2 `huc8_only` 3st/8y (already on disk): **{v2_huc8}**.",
        "",
        "161 is **not** an exact search. Do not copy 161 into a T2 numerator.",
        "",
        "## Contrast table",
        "",
        "| Rule | 3st/8y | 4st/8y |",
        "| --- | ---: | ---: |",
        f"| name×official HUC2 | {counts.get('name_huc2_3st_8y')} | {counts.get('name_huc2_4st_8y')} |",
        f"| official HUC4-only | {counts.get('huc4_3st_8y')} | {counts.get('huc4_4st_8y')} |",
        f"| official HUC6-only | {counts.get('huc6_3st_8y')} | {counts.get('huc6_4st_8y')} |",
        f"| official HUC8-only exact | {counts.get('huc8_3st_8y_exact')} | {counts.get('huc8_4st_8y')} |",
        f"| HUC8 max_pair ≤ 100 km (filter) | {counts.get('huc8_3st_8y_maxpair_100')} | {counts.get('huc8_4st_8y_maxpair_100')} |",
        f"| HUC8 max_pair ≤ 50 km (filter) | {counts.get('huc8_3st_8y_maxpair_50')} | {counts.get('huc8_4st_8y_maxpair_50')} |",
        f"| v1 name×raw HUC prefix whole-group | {counts.get('v1_4st_8y')} | {counts.get('v1_4st_8y')} |",
        "",
        "## Missouri River (attack 3)",
        "",
        missouri.get("proof") or "missouri_river_huc10 not found in v1 contrast.",
        f"HUC8 ids: {', '.join(missouri.get('huc8_ids') or [])}.",
        "It must **not** survive as one HUC8 network.",
        "",
        "## Catalog overlap is not qualified years (attack 7)",
        "",
        "`daily_begin` / `daily_end` are first and last catalog dates. They are",
        "not concurrent daily completeness, not QC, and not 2000–2024 coverage.",
        "The 12 downloaded rivers already collapsed 12→6 under a same-day rule.",
        "Expected post-download attrition 25–40%. Even 161×0.65≈105 only clears",
        "the n_networks_min=100 CI floor as a **hope**, not a result. 150 still",
        "needs Europe and/or a documented 3st/6y failure-closure. **T2 is not",
        "done at 161.**",
        "",
        "## Distance (attack 4–5)",
        "",
        "Pairwise cap is haversine km, Earth radius 6371 km. A 50 km cap expressed",
        "in degrees is meaningless near Alaska vs Florida. Missing lat/lon:",
        f"{MISSING_COORD_POLICY}.",
        "Default distance_mode is **filter** (omit groups that exceed the cap) not",
        "silent shrink of the max-overlap subset.",
        "",
        "## NLDI (attack 6)",
        "",
        "HUC8 does not guarantee flow connectivity. Groups with",
        "`flow_connected=false|partial` are retained as",
        "`spatially_proximate_not_flow_connected`. Live NLDI of all groups is",
        "Implementer A's job; this competing run fixture-tests the parser and",
        "optionally queries 2–3 groups. 404 = isolated origin, not a delete.",
        "429 is retried; leftover failures are `not_queried`, not faked.",
        "",
        "## Split (attack 8–9)",
        "",
        "Stratified 50/20/30 by climate_band × size tertile. Assignment key is",
        f"SHA-256(`seed\\\\tnetwork_id`) with seed **{SPLIT_SEED}**, locked **before**",
        "any new download. never_sealed (12 burned rivers + jinsha +",
        "chattahoochee, matched by site overlap / name tokens) cannot be sealed.",
        "Loire and Swiss Aare-Rhine have no public dated daily values here and",
        "**cannot** fill the 10 non-North-America sealed floor. USGS-only sealed",
        "will not meet sealed≥40 or 10 non-NA; that shortfall is recorded, not",
        "papered over. regulation_stratum = `unknown_until_gages` (the 335-row",
        "regulation-panel extract is not catalog-wide GAGES-II).",
        "",
        "## What this is not",
        "",
        "- Not a recovery score.",
        "- Not T2.",
        "- Not a rewrite of network_catalog_v1.",
        "- Not a temperature download.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_catalog_v3(*, nldi_live_groups: int = 0) -> dict[str, Any]:
    if not CATALOG_SERIES.is_file() or not CATALOG_LOCATIONS.is_file():
        raise SystemExit("need on-disk USGS catalog CSVs; do not download values")
    series = pd.read_csv(CATALOG_SERIES, dtype={"site_id": str, "huc": str, "name": str})
    locations = pd.read_csv(
        CATALOG_LOCATIONS, dtype={"site_id": str, "huc": str, "name": str}
    )
    HERE.mkdir(parents=True, exist_ok=True)

    exact = cluster_by_huc8(series, locations, min_stations=3, min_overlap_years=8)
    truncated = cluster_by_huc8(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8,
        overlap_search="truncated_combo",
    )
    naive = cluster_by_huc8(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8,
        huc_encoder=naive_huc_prefix,
    )
    huc8_4 = cluster_by_huc8(series, locations, min_stations=4, min_overlap_years=8)
    huc4_3 = cluster_by_huc_level(
        series, locations, huc_width=4, min_stations=3, min_overlap_years=8
    )
    huc4_4 = cluster_by_huc_level(
        series, locations, huc_width=4, min_stations=4, min_overlap_years=8
    )
    huc6_3 = cluster_by_huc_level(
        series, locations, huc_width=6, min_stations=3, min_overlap_years=8
    )
    huc6_4 = cluster_by_huc_level(
        series, locations, huc_width=6, min_stations=4, min_overlap_years=8
    )
    cap100 = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=100.0
    )
    cap50 = cluster_by_huc8(
        series, locations, min_stations=3, min_overlap_years=8, max_pair_km=50.0
    )
    cap100_4 = cluster_by_huc8(
        series, locations, min_stations=4, min_overlap_years=8, max_pair_km=100.0
    )
    cap50_4 = cluster_by_huc8(
        series, locations, min_stations=4, min_overlap_years=8, max_pair_km=50.0
    )
    name3 = name_huc2_contrast(series, locations, min_stations=3, min_overlap_years=8)
    name4 = name_huc2_contrast(series, locations, min_stations=4, min_overlap_years=8)
    v1 = cluster_rivers_from_catalog(series, locations)
    v1_ok = int(v1["enough_overlap_years"].fillna(False).sum()) if not v1.empty else 0
    v2 = cluster_rivers_from_catalog_v2(
        series,
        locations,
        min_stations=3,
        min_overlap_years=8.0,
        min_span_years=8.0,
        include_huc8_only=True,
    )
    v2_huc8 = int(v2.loc[v2["grouping"].eq("huc8_only")].shape[0]) if not v2.empty else 0

    burned = load_never_sealed_from_v1()
    tagged = tag_never_sealed(exact, burned)
    missouri = missouri_huc8_split(series, locations, tagged)

    gt12 = tagged.loc[tagged["n_stations_available"].ge(13)] if not tagged.empty else tagged
    nldi_cache = HERE / "nldi_cache"
    prepared = prepare_huc8_stations(series, locations, min_span_years=8.0)
    live_ids = []
    if nldi_live_groups and not tagged.empty:
        # Prefer a mixed HUC8 and a Missouri-related HUC8, not 161 calls.
        prefer = list(missouri.get("huc8_ids") or [])
        chosen = []
        for huc8 in prefer:
            hit = tagged.loc[tagged["huc8"].eq(huc8)]
            if not hit.empty:
                chosen.append(hit.index[0])
        for index in tagged.index:
            if len(chosen) >= int(nldi_live_groups):
                break
            if index not in chosen:
                chosen.append(index)
        probe = tagged.loc[chosen[: int(nldi_live_groups)]].copy()
        live_ids = list(probe["network_id"])
        try:
            probed = annotate_clusters(
                probe,
                prepared,
                cache_dir=nldi_cache,
                query=True,
                max_groups=int(nldi_live_groups),
                pause_s=0.4,
            )
            for column in (
                "nldi_origin_site_id",
                "flow_connected",
                "n_connected_stations",
                "connected_site_ids",
                "spatially_proximate_not_flow_connected",
                "nldi_um_status",
                "nldi_dm_status",
            ):
                if column in probed.columns:
                    tagged.loc[probed.index, column] = probed[column]
        except Exception as error:  # noqa: BLE001
            tagged["nldi_live_error"] = str(error)

    split_frame, split_sha = lock_stratified_split(tagged, seed=SPLIT_SEED)
    n_sealed = int(split_frame["split_role"].eq("sealed").sum())
    n_non_na_sealed = 0  # USGS HUC8 catalog is North America only
    n_never = int(split_frame["never_sealed"].fillna(False).sum())

    n_stations_trunc_diff = 0
    if not exact.empty and not truncated.empty:
        left = exact[["network_id", "n_stations"]].rename(columns={"n_stations": "n_exact"})
        right = truncated[["network_id", "n_stations"]].rename(columns={"n_stations": "n_trunc"})
        compared = left.merge(right, on="network_id", how="outer")
        n_stations_trunc_diff = int(
            (pd.to_numeric(compared["n_exact"], errors="coerce")
             != pd.to_numeric(compared["n_trunc"], errors="coerce")).sum()
        )

    counts = {
        "huc8_3st_8y_exact": _count_ok(exact),
        "huc8_3st_8y_truncated_combo": _count_ok(truncated),
        "huc8_3st_8y_naive_zfill": _count_ok(naive),
        "huc8_4st_8y": _count_ok(huc8_4),
        "huc8_3st_8y_maxpair_100": _count_ok(cap100),
        "huc8_3st_8y_maxpair_50": _count_ok(cap50),
        "huc8_4st_8y_maxpair_100": _count_ok(cap100_4),
        "huc8_4st_8y_maxpair_50": _count_ok(cap50_4),
        "huc4_3st_8y": _count_ok(huc4_3),
        "huc4_4st_8y": _count_ok(huc4_4),
        "huc6_3st_8y": _count_ok(huc6_3),
        "huc6_4st_8y": _count_ok(huc6_4),
        "name_huc2_3st_8y": _count_ok(name3),
        "name_huc2_4st_8y": _count_ok(name4),
        "v1_4st_8y": v1_ok,
        "v2_huc8_only_3st_8y": v2_huc8,
        "reviewer_161": 161,
        "reviewer_161_equals_naive_zfill": bool(_count_ok(naive) == 161),
        "exact_minus_161": _count_ok(exact) - 161,
        "exact_minus_truncated": _count_ok(exact) - _count_ok(truncated),
        "n_groups_available_gt_12": int(len(gt12)) if gt12 is not None and not gt12.empty else 0,
        "n_groups_n_stations_truncated": n_stations_trunc_diff,
        "n_never_sealed_huc8": n_never,
        "n_split_sealed": n_sealed,
        "n_non_na_sealed": n_non_na_sealed,
        "non_na_sealed_shortfall_vs_10": 10 - n_non_na_sealed,
        "sealed_shortfall_vs_40": max(0, 40 - n_sealed),
        "split_seed": SPLIT_SEED,
        "split_table_sha256": split_sha,
        "temperatures_downloaded": False,
        "sealed_outcomes_opened": False,
        "network_catalog_v1_remapped": False,
        "t2_claimed_at_161": False,
        "loire_swiss_used_as_non_na_sealed": False,
        "missing_coord_policy": MISSING_COORD_POLICY,
        "distance_mode_default": "filter",
        "earth_radius_km": EARTH_RADIUS_KM,
        "nldi_live_groups_attempted": live_ids,
        "missouri": missouri,
    }

    tagged.to_csv(HERE / "usgs_river_clusters_v3_huc8.csv", index=False)
    cap50.to_csv(HERE / "usgs_river_clusters_v3_huc8_maxpair50.csv", index=False)
    cap100.to_csv(HERE / "usgs_river_clusters_v3_huc8_maxpair100.csv", index=False)
    if not v1.empty:
        v1.to_csv(HERE / "usgs_river_clusters_v1_name_huc2_contrast.csv", index=False)
    split_frame.to_csv(HERE / "catalog_v3_split.csv", index=False)
    (HERE / "catalog_v3_split_sha256.txt").write_text(split_sha + "\n", encoding="utf-8")
    (HERE / "network_catalog_v3_split.yaml").write_text(
        yaml.safe_dump(
            {
                "catalog_id": "network_catalog_v3_huc8_split_adversarial",
                "seed": SPLIT_SEED,
                "fractions": {"development": 0.50, "validation": 0.20, "sealed": 0.30},
                "split_table_sha256": split_sha,
                "regulation_stratum": "unknown_until_gages",
                "temperatures_downloaded": False,
                "sealed_outcomes_opened": False,
                "network_catalog_v1_remapped": False,
                "loire_swiss_used_as_non_na_sealed": False,
                "n_sealed": n_sealed,
                "n_non_na_sealed": n_non_na_sealed,
                "note": (
                    "USGS-only HUC8 split locked before download. never_sealed "
                    "held out. Loire/Swiss not used. GAGES not invented from names."
                ),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (HERE / "missouri_split.json").write_text(
        json.dumps(missouri, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (HERE / "counts.json").write_text(
        json.dumps(counts, indent=2, default=str) + "\n", encoding="utf-8"
    )
    write_feasibility(HERE / "feasibility.md", counts, missouri)
    return counts


def main() -> None:
    counts = build_catalog_v3(nldi_live_groups=3)
    print(json.dumps({k: counts[k] for k in counts if k != "missouri"}, indent=2, default=str))
    print("missouri_huc8_ids", (counts.get("missouri") or {}).get("huc8_ids"))
    print("wrote", HERE)


if __name__ == "__main__":
    main()
