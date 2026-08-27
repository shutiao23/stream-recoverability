"""Toy UK EA spatial clustering: 50 km max-pair analog of HUC8.

Name clustering on the UK EA catalog found one 3-station river (Derwent)
because 1948/1964 rows have a blank riverName. The required next catalog
move is geodesic clustering on lat/lon with a 50 km complete-linkage cap.

A spatial catalog cluster is still not T8. Do not download the full 1964
reading archive from this helper. Do not treat dateOpened as daily years.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from w6_contract import (
    MIN_STATIONS,
    t8_countable,
)

EARTH_RADIUS_KM = 6371.0
MAX_PAIR_KM = 50.0


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


def name_clusters(
    stations: pd.DataFrame,
    *,
    min_stations: int = MIN_STATIONS,
    river_col: str = "river",
) -> pd.DataFrame:
    """UK EA production clustering: non-blank riverName groups of size ≥ 3."""

    if stations.empty or river_col not in stations.columns:
        return pd.DataFrame(columns=["river", "n_stations", "site_ids", "countable_toward_t8"])
    frame = stations.copy()
    frame[river_col] = frame[river_col].fillna("").astype(str).str.strip()
    named = frame.loc[frame[river_col].ne("")]
    rows: list[dict[str, Any]] = []
    for river, group in named.groupby(river_col, sort=False):
        if len(group) < int(min_stations):
            continue
        site_col = "site_id" if "site_id" in group.columns else group.columns[0]
        rows.append(
            {
                "river": river,
                "n_stations": int(len(group)),
                "site_ids": ",".join(str(item) for item in group[site_col]),
                "method": "name",
                "countable_toward_t8": False,
                "catalog_cluster_only": True,
            }
        )
    return pd.DataFrame(rows)


def spatial_clusters_50km(
    stations: pd.DataFrame,
    *,
    max_pair_km: float = MAX_PAIR_KM,
    min_stations: int = MIN_STATIONS,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    id_col: str = "site_id",
) -> pd.DataFrame:
    """Complete-linkage clusters with max pairwise geodesic distance ≤ cap.

    Analog of the HUC8 max-pair 50 km diagnostic. Missing coordinates are
    dropped, never treated as 0 km or inf km. Output rows are catalog
    candidates, not T8 networks.
    """

    if stations.empty:
        return pd.DataFrame()
    frame = stations.copy()
    frame["_lat"] = pd.to_numeric(frame.get(lat_col), errors="coerce")
    frame["_lon"] = pd.to_numeric(frame.get(lon_col), errors="coerce")
    located = frame.loc[frame["_lat"].notna() & frame["_lon"].notna()].reset_index(drop=True)
    n = len(located)
    assigned = [False] * n
    rows: list[dict[str, Any]] = []
    cluster_i = 0
    for i in range(n):
        if assigned[i]:
            continue
        members = [i]
        assigned[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(n):
                if assigned[j]:
                    continue
                if max(
                    geodesic_km(
                        located.at[j, "_lat"],
                        located.at[j, "_lon"],
                        located.at[m, "_lat"],
                        located.at[m, "_lon"],
                    )
                    for m in members
                ) <= float(max_pair_km):
                    members.append(j)
                    assigned[j] = True
                    changed = True
        if len(members) < int(min_stations):
            continue
        pair_km = []
        for a, left in enumerate(members):
            for right in members[a + 1 :]:
                pair_km.append(
                    geodesic_km(
                        located.at[left, "_lat"],
                        located.at[left, "_lon"],
                        located.at[right, "_lat"],
                        located.at[right, "_lon"],
                    )
                )
        site_ids = [str(located.at[m, id_col]) for m in members]
        cluster_i += 1
        rivers = (
            located.loc[members, "river"].fillna("").astype(str).str.strip()
            if "river" in located.columns
            else pd.Series([""] * len(members))
        )
        rows.append(
            {
                "cluster_id": f"spatial50_{cluster_i:03d}",
                "n_stations": len(members),
                "site_ids": ",".join(site_ids),
                "max_pair_km": float(max(pair_km) if pair_km else 0.0),
                "n_named_river": int(rivers.ne("").sum()),
                "method": "spatial_50km",
                "countable_toward_t8": t8_countable(
                    n_stations=len(members),
                    overlapping_daily_years=0.0,
                    catalog_cluster_only=True,
                ),
                "catalog_cluster_only": True,
            }
        )
    return pd.DataFrame(rows)


def toy_uk_stations() -> pd.DataFrame:
    """Eight rows: one unnamed 50 km clump, one named Derwent pair, two isolates.

    Spatial clustering must recover the unnamed triplet that name clustering
    drops. The named pair is below the 3-station floor. Isolates stay out.
    """

    return pd.DataFrame(
        [
            {
                "site_id": "unnamed_a",
                "river": "",
                "latitude": 53.00,
                "longitude": -1.50,
                "date_opened": "1970-01-01",
            },
            {
                "site_id": "unnamed_b",
                "river": "",
                "latitude": 53.05,
                "longitude": -1.50,
                "date_opened": "1980-01-01",
            },
            {
                "site_id": "unnamed_c",
                "river": "",
                "latitude": 53.10,
                "longitude": -1.48,
                "date_opened": "1990-01-01",
            },
            {
                "site_id": "derwent_1",
                "river": "River Derwent",
                "latitude": 52.88,
                "longitude": -1.35,
                "date_opened": "1973-05-01",
            },
            {
                "site_id": "derwent_2",
                "river": "River Derwent",
                "latitude": 52.93,
                "longitude": -1.47,
                "date_opened": "1935-10-02",
            },
            {
                "site_id": "far_scotland",
                "river": "",
                "latitude": 57.15,
                "longitude": -2.10,
                "date_opened": "1964-01-01",
            },
            {
                "site_id": "far_cornwall",
                "river": "",
                "latitude": 50.26,
                "longitude": -5.05,
                "date_opened": "1964-01-01",
            },
            {
                "site_id": "avon_only",
                "river": "River Avon",
                "latitude": 52.09,
                "longitude": -1.94,
                "date_opened": "1936-12-01",
            },
        ]
    )


def toy_too_wide_for_50km() -> pd.DataFrame:
    """Three named stations on a 120 km baseline: name cluster yes, spatial no."""

    return pd.DataFrame(
        [
            {
                "site_id": "wide_a",
                "river": "River Wide",
                "latitude": 53.00,
                "longitude": -1.00,
            },
            {
                "site_id": "wide_b",
                "river": "River Wide",
                "latitude": 53.00,
                "longitude": -1.90,
            },
            {
                "site_id": "wide_c",
                "river": "River Wide",
                "latitude": 53.80,
                "longitude": -1.00,
            },
        ]
    )


if __name__ == "__main__":
    toy = toy_uk_stations()
    named = name_clusters(toy)
    spatial = spatial_clusters_50km(toy)
    print("name clusters:")
    print(named.to_string(index=False) if not named.empty else "(none)")
    print("spatial 50 km clusters:")
    print(spatial.to_string(index=False) if not spatial.empty else "(none)")
    print("any spatial countable_toward_t8:", bool(spatial["countable_toward_t8"].any()) if not spatial.empty else False)
